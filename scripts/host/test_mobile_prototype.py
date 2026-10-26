"""Real TCP/serial-owner code with an explicitly simulated firmware/model fixture."""
import json
import re
import threading
import unittest

from mobile_prototype_gateway import PrototypeBoard, PrototypeGateway
from mobile_serial_gateway import SerialBroker, GatewayError
from test_mobile_serial_gateway import FakeSerial, Client


class SensitivitySerial(FakeSerial):
    def __init__(self):
        super().__init__()
        self.profile='standard'
        self.mutations=0
        self.bad_ack=False

    def write(self, wire):
        if wire.startswith(b'@snapshot '):return super().write(wire)
        with self.condition:
            m=re.fullmatch(rb'@sensitivity ([A-Za-z0-9_-]{1,48}) (get|standard|early)\r\n',wire)
            assert m, 'Unexpected serial operation'
            self.writes.append(wire)
            request_id,op=(s.decode() for s in m.groups())
            if op!='get':self.profile=op;self.mutations+=1
            response={'v':1,'id':request_id,'ok':True,'profile':self.profile,
                      'factor':1.25 if self.profile=='early' else 1,'volatile':True}
            if self.bad_ack:response['factor']=9
            self.buffer.extend(b'[ew-sensitivity] '+json.dumps(response).encode()+b'\r\n')
            self.condition.notify_all()
            return len(wire)


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        self.serial=SensitivitySerial()
        self.broker=SerialBroker(self.serial,timeout_s=.8,enable_sensitivity=True)
        self.board=PrototypeBoard(self.broker)
        self.calls=[]
        def model(text,state):
            self.calls.append(text)
            return 'EXPLICIT MODEL FIXTURE; no real model'
        self.server=PrototypeGateway(self.board,model,port=0,fixture_state=True)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
        self.thread.start()
        self.client=Client(self.server.address)
        self.addCleanup(self.clean)

    def clean(self):
        self.client.close();self.server.shutdown();self.server.server_close();self.thread.join(1)

    def final(self,request_id):
        while True:
            result=self.client.result(request_id)
            if result['type']=='result':return result

    def hello(self):
        self.client.send('hello','hello')
        result=self.final('hello')
        self.assertTrue(result['ok'])
        return result['data']

    def test_hello_demands_firmware_config_and_marks_fixture(self):
        data=self.hello()
        self.assertEqual(data['origin'],'pc_prototype')
        self.assertTrue(data['fixture_state'])
        self.assertNotIn('test_alert',data['capabilities'])
        self.assertTrue(any(x.startswith(b'@sensitivity ') for x in self.serial.writes))

    def test_standard_gateway_broker_does_not_enable_mutations(self):
        other=SerialBroker(FakeSerial())
        try:
            with self.assertRaises(GatewayError):other.sensitivity('early')
        finally:other.close()

    def test_set_applies_and_reads_back_before_success(self):
        self.hello();self.client.send('set1','set_profile',{'profile':'early'})
        self.assertEqual(self.client.result('set1')['stage'],'queued')
        data=self.final('set1')['data']
        self.assertEqual(data['profile'],'early')
        self.assertTrue(data['device_confirmed'])
        self.assertTrue(self.serial.writes[-1].endswith(b' get\r\n'))
        self.client.send('state','get_state')
        self.assertEqual(self.final('state')['data']['profile'],'early')

    def test_duplicate_effect_and_id_conflict(self):
        self.hello()
        for _ in range(2):
            self.client.send('repeat','set_profile',{'profile':'early'});self.final('repeat')
        self.assertEqual(self.serial.mutations,1)
        self.client.send('repeat','set_profile',{'profile':'standard'})
        self.assertEqual(self.final('repeat')['error']['code'],'id_conflict')
        self.assertEqual(self.serial.mutations,1)

    def test_model_fixture_is_explicit_and_cached(self):
        self.hello()
        for _ in range(2):
            self.client.send('ask','ask',{'text':'test'})
            data=self.final('ask')['data']
            self.assertTrue(data['model_simulated'])
        self.assertEqual(self.calls,['test'])

    def test_invalid_or_unnegotiated_operations_never_write(self):
        self.client.send('before','set_profile',{'profile':'early'})
        self.assertFalse(self.final('before')['ok'])
        self.hello()
        for op,args in [('set_profile',{'profile':'unsafe'}),('test_alert',{}),('ask',{'text':''})]:
            self.client.send(op,op,args);self.assertFalse(self.final(op)['ok'])
        self.assertEqual(self.serial.mutations,0)
        self.assertEqual(self.calls,[])

    def test_bad_firmware_ack_cannot_report_applied(self):
        self.hello();self.serial.bad_ack=True
        self.client.send('bad','set_profile',{'profile':'early'})
        self.assertFalse(self.final('bad')['ok'])

    def test_paired_session_requires_correct_code_before_any_control(self):
        self.server.pair_code='testSessionCode1234'
        self.client.send('missing','hello')
        self.assertEqual(self.final('missing')['error']['code'],'unauthorized')
        self.client.send('wrong','hello',{'token':'wrong'})
        self.assertEqual(self.final('wrong')['error']['code'],'unauthorized')
        self.assertEqual(self.serial.mutations,0)
        self.client.send('paired','hello',{'token':'testSessionCode1234'})
        data=self.final('paired')['data']
        self.assertTrue(data['paired'])
        self.assertEqual(data['transport'],'paired_lan')

    def test_unrestricted_or_unpaired_bind_is_rejected(self):
        for host in ('0.0.0.0','192.168.43.2'):
            with self.assertRaises(ValueError):
                PrototypeGateway(self.board,lambda *_:'fixture',port=0,listen_host=host)


if __name__=='__main__':unittest.main(verbosity=2)
