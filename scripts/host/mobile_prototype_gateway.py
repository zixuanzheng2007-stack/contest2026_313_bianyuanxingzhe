#!/usr/bin/env python3
"""PC prototype: board sensitivity + PC-to-MiMo; injectable fixtures for tests.

Defaults to loopback. An explicit LAN interface requires a session pairing code
and allowed client addresses. The original gateway remains read-only.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import json
import ipaddress
import os
import secrets
import threading
import time
import urllib.error
import urllib.request

from mobile_device_simulator import _decode_request, _error, _result, ProtocolError
from mobile_serial_gateway import MobileSerialGateway, SerialBroker, GatewayError, MAX_MESSAGE_BYTES

CAPABILITIES = ['get_state', 'subscribe_state', 'get_config', 'set_profile', 'ask']


class PrototypeBoard:
    def __init__(self, broker):
        self.broker = broker
        self.timeout_s = broker.timeout_s
        self.profile = None

    def config(self, setting='get'):
        value = self.broker.sensitivity(setting)
        # Read back after mutation, rather than trusting the outgoing request.
        if setting != 'get':
            confirmed = self.broker.sensitivity('get')
            if confirmed['profile'] != value['profile']:
                raise GatewayError('execution_failed', 'Sensitivity readback did not match.')
            value = confirmed
        self.profile = value['profile']
        return {'origin':'pc_prototype', 'profile':value['profile'], 'factor':value['factor'],
                'volatile':True, 'device_confirmed':True}

    def query(self):
        state = self.broker.query()
        state.update(origin='pc_prototype', profile=self.profile)
        return state

    def close(self):
        self.broker.close()


class MiMoClient:
    def __init__(self, key, model='mimo-v2.6-flash'):
        if not key:
            raise ValueError('Existing MIMO_API_KEY is required; never pass it in CLI arguments.')
        self.key, self.model = key, model

    def __call__(self, text, state):
        payload = {'model':self.model, 'stream':False, 'max_completion_tokens':384,
                   'messages':[{'role':'system','content':
                                '你是边缘行者演示助手。用中文简短回答。以下快照是唯一设备事实；'
                                'null表示缺测，不推断安全。没有工具执行能力，不声称修改设备。'
                                '请求由电脑转发。设备快照：'+json.dumps(state,ensure_ascii=False)},
                               {'role':'user','content':text}]}
        request = urllib.request.Request('https://token-plan-cn.xiaomimimo.com/v1/chat/completions',
            data=json.dumps(payload,ensure_ascii=False).encode(),
            headers={'api-key':self.key,'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=40) as response:
                wire = response.read(65537)
            if len(wire)>65536:
                raise GatewayError('model_failed','Model response exceeded limit.')
            value=json.loads(wire)
            reply=value['choices'][0]['message']['content']
            if not isinstance(reply,str) or not reply.strip():
                raise ValueError('empty reply')
            return reply.encode()[:3072].decode('utf-8',errors='ignore')
        except urllib.error.HTTPError as exc:
            raise GatewayError('model_failed','MiMo HTTP '+str(exc.code)) from None
        except (OSError,ValueError,KeyError,IndexError,TypeError):
            raise GatewayError('model_failed','MiMo request failed or timed out.') from None


class PrototypeGateway(MobileSerialGateway):
    def __init__(self, board, model, *, port=8767, fixture_state=False,
                 listen_host='127.0.0.1', pair_code=None, allowed_clients=()):
        address=ipaddress.ip_address(listen_host)
        if address.version!=4 or address.is_unspecified or address.is_multicast:
            raise ValueError('Choose one explicit IPv4 interface, never all interfaces.')
        if pair_code is not None and (len(pair_code)<12 or len(pair_code)>64
                                     or not pair_code.isascii() or not pair_code.isalnum()):
            raise ValueError('Pair code must contain 12-64 ASCII letters/digits.')
        if not address.is_loopback and (not pair_code or not allowed_clients):
            raise ValueError('Non-loopback prototype requires a session code and explicit clients.')
        self.listen_host=listen_host
        self.pair_code=pair_code
        self.allowed_clients={str(ipaddress.ip_address(ip)) for ip in allowed_clients}
        self._bad_pairings={}
        self.model = model
        self.fixture_state = fixture_state
        self._effect_lock = threading.Lock()
        self._results = OrderedDict()
        super().__init__(board,host='127.0.0.1',port=port,max_clients=4,
                         subscription_interval_s=2,cache_capacity=256)
        self._model_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ew-model')
        self._model_pending = None

    def server_bind(self):
        # Only this paired subclass can bind an explicitly chosen interface.
        # The original read-only service retains its loopback-only policy.
        self.server_address=(self.listen_host,self.server_address[1])
        return super().server_bind()

    def _register(self,connection):
        peer=connection.socket.getpeername()[0]
        if self.allowed_clients and peer not in self.allowed_clients:
            return False
        return super()._register(connection)

    def _handle_line(self, connection, line):
        request_id = None
        try:
            request_id, op, args, fingerprint = _decode_request(line)
            self._record(request_id,fingerprint)
            if op == 'hello':
                if self.pair_code is not None:
                    peer=connection.socket.getpeername()[0]
                    supplied=args.get('token')
                    if (set(args)!={'token'} or not isinstance(supplied,str)
                            or not secrets.compare_digest(supplied.encode(),self.pair_code.encode())):
                        with self._guard:
                            self._bad_pairings[peer]=self._bad_pairings.get(peer,0)+1
                            attempts=self._bad_pairings[peer]
                        connection.send(_error(request_id,'unauthorized','Session pairing code is missing or incorrect.'))
                        if attempts>=5:connection.close()
                        return
                    if self._bad_pairings.get(peer,0)>=5:
                        raise GatewayError('unauthorized','Pairing attempts exceeded; restart the test session.')
                elif args:
                    raise GatewayError('invalid_args','hello takes no arguments.')
                self.broker.config()
                self.broker.query()
                connection.prototype_ready=True
                connection.send(_result(request_id,{'origin':'pc_prototype','device_id':'ew-usb-prototype',
                    'capabilities':CAPABILITIES,'max_message_bytes':MAX_MESSAGE_BYTES,
                    'prototype':True,'fixture_state':self.fixture_state,'read_only':False,
                    'transport':'paired_lan' if self.pair_code is not None else 'authorized_usb_loopback',
                    'paired':self.pair_code is not None,'model_source':'pc_cloud'}))
                return
            if not getattr(connection,'prototype_ready',False):
                raise GatewayError('not_connected','Complete hello first.')
            expected={'subscribe_state':{'enabled'},'set_profile':{'profile'},'ask':{'text'}}.get(op,set())
            if op not in CAPABILITIES:
                raise GatewayError('unsupported','Operation is outside the prototype allowlist.')
            if set(args)!=expected:
                raise GatewayError('invalid_args','Unexpected or missing arguments.')
            if op == 'get_state':
                connection.send(_result(request_id,self.broker.query()))
            elif op == 'get_config':
                connection.send(_result(request_id,self.broker.config()))
            elif op == 'subscribe_state':
                if type(args['enabled']) is not bool:
                    raise GatewayError('invalid_args','enabled must be boolean.')
                connection.subscription_id=request_id
                connection.subscription_result(args['enabled'],_result(request_id,
                    {'origin':'pc_prototype','enabled':args['enabled']}))
            else:
                if op=='set_profile' and args['profile'] not in ('standard','early'):
                    raise GatewayError('invalid_args','Only standard and early presets are allowed.')
                if op=='ask' and (not isinstance(args['text'],str) or not args['text'].strip()
                                  or len(args['text'].encode())>1024):
                    raise GatewayError('invalid_args','Question must be 1-1024 UTF-8 bytes.')
                if op == 'ask':
                    self._submit_model(connection, request_id, fingerprint, args['text'])
                    return
                # Serializes side effects across clients and caches final results.
                # No device command is retransmitted when a response is uncertain.
                with self._effect_lock:
                    with self._guard:
                        cached = self._results.get(request_id)
                    if cached is not None:
                        previous, result = cached
                        if previous != fingerprint:
                            raise GatewayError('id_conflict','Request ID has different content.')
                        connection.send(result);return
                    connection.send({'v':1,'id':request_id,'type':'accepted','ok':True,'stage':'queued'})
                    try:
                        started=time.perf_counter()
                        data=self.broker.config(args['profile'])
                        data['elapsed_ms']=round((time.perf_counter()-started)*1000)
                        result=_result(request_id,data)
                    except GatewayError as exc:
                        result=_error(request_id,exc.code,str(exc))
                    with self._guard:
                        self._results[request_id]=(fingerprint,result)
                        while len(self._results)>64:self._results.popitem(last=False)
                    connection.send(result)
        except (GatewayError,ProtocolError) as exc:
            connection.send(_error(request_id,exc.code,str(exc)))
        except (UnicodeError,ValueError):
            connection.send(_error(request_id,'invalid_args','Invalid text input.'))

    def _submit_model(self, connection, request_id, fingerprint, text):
        # One bounded cloud request; socket readers and sensitivity remain free.
        with self._guard:
            cached = self._results.get(request_id)
            if cached is not None:
                if cached[0] != fingerprint:
                    raise GatewayError('id_conflict', 'Request ID has different content.')
                connection.send(cached[1])
                return
            if self._model_pending is not None:
                pending_id, pending_fingerprint, listeners = self._model_pending
                if pending_id != request_id:
                    raise GatewayError('busy', 'A model question is already running; retry later.')
                if pending_fingerprint != fingerprint:
                    raise GatewayError('id_conflict', 'Request ID has different content.')
                # At most four live clients; repeated sends add no listeners.
                listeners.intersection_update(self._connections)
                listeners.add(connection)
                connection.send({'v':1,'id':request_id,'type':'accepted','ok':True,'stage':'queued'})
                return
            if self.stopping.is_set():
                raise GatewayError('busy', 'Prototype service is stopping.')
            self._model_pending = (request_id, fingerprint, {connection})
            connection.send({'v':1,'id':request_id,'type':'accepted','ok':True,'stage':'queued'})
            self._model_executor.submit(self._finish_model, request_id, fingerprint, text)

    def _finish_model(self, request_id, fingerprint, text):
        started = time.perf_counter()
        try:
            data = {'origin':'pc_prototype', 'reply':self.model(text, self.broker.query()),
                    'model_source':'pc_cloud', 'model_simulated':self.fixture_state,
                    'elapsed_ms':round((time.perf_counter()-started)*1000)}
            result = _result(request_id, data)
        except GatewayError as exc:
            result = _error(request_id, exc.code, str(exc))
        except Exception:
            # Never expose credentials or provider response bodies in errors.
            result = _error(request_id, 'model_failed', 'Model request failed.')
        with self._guard:
            listeners = self._model_pending[2]
            self._results[request_id] = (fingerprint, result)
            while len(self._results)>64:self._results.popitem(last=False)
            self._model_pending = None
        for connection in listeners:
            connection.send(result)

    def server_close(self):
        super().server_close()
        if hasattr(self, '_model_executor'):
            self._model_executor.shutdown(wait=True)

    def _publish_loop(self):
        while not self.stopping.wait(self.subscription_interval_s):
            with self._guard:
                subscribers=[c for c in self._connections if c.subscribed and not c.closed.is_set()]
            if not subscribers:continue
            try:state=self.broker.query()
            except GatewayError as exc:
                if exc.code=='busy':continue
                for c in subscribers:
                    c.send(_error(c.subscription_id,exc.code,str(exc)));c.close()
                continue
            event={'v':1,'type':'event','event':'state','source':'pc_prototype',
                   'event_id':state['snapshot_seq'],'data':state}
            for c in subscribers:c.send(event,subscription=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True,help='Explicit physical board COM port')
    parser.add_argument('--listen-port',type=int,default=8767)
    parser.add_argument('--listen-host',default='127.0.0.1')
    parser.add_argument('--allow-client',action='append',default=[])
    args=parser.parse_args()
    from board_snapshot_acceptance import _open_serial
    from mimo_configure import read_secret
    model=MiMoClient(read_secret('MIMO_API_KEY'))
    broker=SerialBroker(_open_serial(args.port),timeout_s=2,enable_sensitivity=True)
    board=PrototypeBoard(broker)
    server=None
    try:
        board.config()  # Refuse old firmware before advertising any controls.
        server=PrototypeGateway(board,model,port=args.listen_port,listen_host=args.listen_host,
                                pair_code=os.environ.get('EW_PROTOTYPE_PAIR_CODE'),
                                allowed_clients=args.allow_client)
        print(json.dumps({'origin':'pc_prototype','listening':server.address,
                          'model_source':'pc_cloud','simulated':False}),flush=True)
        server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt:pass
    finally:
        if server is not None:server.server_close()
        else:board.close()


if __name__=='__main__':main()
