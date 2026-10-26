#!/usr/bin/env python3
"""Connect one Windows Wi-Fi adapter to a supplied lab hotspot; rollback on failure.

Password is read only from EW_TEST_PASSWORD; XML stays in RAM. Adds one manual,
current-user profile, never edits existing profiles or restarts networking.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
import uuid
from xml.sax.saxutils import escape


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface-guid',required=True)
    p.add_argument('--ssid',required=True)
    p.add_argument('--prefix',default='192.168.43.')
    args=p.parse_args()
    password=os.environ.pop('EW_TEST_PASSWORD')
    class GUID(C.Structure):
        _fields_=[('a',W.DWORD),('b',W.WORD),('c',W.WORD),('d',C.c_ubyte*8)]
    class Params(C.Structure):
        _fields_=[('mode',W.DWORD),('profile',W.LPCWSTR),('ssid',C.c_void_p),
                  ('bssids',C.c_void_p),('bss_type',W.DWORD),('flags',W.DWORD)]
    dll=C.WinDLL('wlanapi.dll')
    dll.WlanOpenHandle.argtypes=[W.DWORD,C.c_void_p,C.POINTER(W.DWORD),C.POINTER(W.HANDLE)]
    dll.WlanQueryInterface.argtypes=[W.HANDLE,C.POINTER(GUID),W.DWORD,C.c_void_p,
                                    C.POINTER(W.DWORD),C.POINTER(C.c_void_p),C.POINTER(W.DWORD)]
    dll.WlanSetProfile.argtypes=[W.HANDLE,C.POINTER(GUID),W.DWORD,W.LPCWSTR,W.LPCWSTR,
                                W.BOOL,C.c_void_p,C.POINTER(W.DWORD)]
    dll.WlanConnect.argtypes=[W.HANDLE,C.POINTER(GUID),C.POINTER(Params),C.c_void_p]
    dll.WlanDeleteProfile.argtypes=[W.HANDLE,C.POINTER(GUID),W.LPCWSTR,C.c_void_p]
    dll.WlanFreeMemory.argtypes=[C.c_void_p]
    dll.WlanCloseHandle.argtypes=[W.HANDLE,C.c_void_p]
    handle=W.HANDLE();version=W.DWORD()
    guid=GUID.from_buffer_copy(uuid.UUID(args.interface_guid.strip('{}')).bytes_le)
    def checked(rc):
        if rc:raise OSError('Windows WLAN error '+str(rc))
    checked(dll.WlanOpenHandle(2,None,C.byref(version),C.byref(handle)))
    original=None;created=False;connected=False
    profile='EdgeWalker-Test-'+secrets.token_hex(4)
    report={'credential_logged':False,'profile_created':profile,'success':False}
    def connect(name):
        parameters=Params(0,name,None,None,1,0)
        checked(dll.WlanConnect(handle,C.byref(guid),C.byref(parameters),None))
    try:
        size=W.DWORD();data=C.c_void_p();kind=W.DWORD()
        checked(dll.WlanQueryInterface(handle,C.byref(guid),7,None,C.byref(size),C.byref(data),C.byref(kind)))
        try:
            if size.value<520:raise OSError('Unexpected WLAN connection metadata')
            original=C.wstring_at(data.value+8,256).split('\0',1)[0]
        finally:dll.WlanFreeMemory(data)
        report['original_profile']=original
        xml=('<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
             '<name>'+profile+'</name><SSIDConfig><SSID><name>'+escape(args.ssid)+'</name></SSID></SSIDConfig>'
             '<connectionType>ESS</connectionType><connectionMode>manual</connectionMode><MSM><security>'
             '<authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption>'
             '<useOneX>false</useOneX></authEncryption><sharedKey><keyType>passPhrase</keyType>'
             '<protected>false</protected><keyMaterial>'+escape(password)+'</keyMaterial></sharedKey>'
             '</security></MSM></WLANProfile>')
        reason=W.DWORD()
        checked(dll.WlanSetProfile(handle,C.byref(guid),2,xml,None,False,None,C.byref(reason)))
        created=True;connect(profile)
        end=time.monotonic()+25
        address=None
        while time.monotonic()<end:
            r=subprocess.run(['powershell','-NoProfile','-Command',
                              "Get-NetIPAddress -InterfaceAlias WLAN -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress"],
                             capture_output=True,timeout=5)
            address=next((line.strip() for line in r.stdout.decode(errors='replace').splitlines()
                          if line.strip().startswith(args.prefix)),None)
            if address:break
            time.sleep(1)
        if not address:raise OSError('Hotspot DHCP did not complete')
        report['hotspot_ip']=address
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from mimo_configure import read_secret
        request=urllib.request.Request('https://token-plan-cn.xiaomimimo.com/v1/models',
                                       headers={'api-key':read_secret('MIMO_API_KEY')})
        # DHCP can finish before DNS/proxy routes settle after a Wi-Fi switch.
        last_error=None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request,timeout=8) as response:
                    if response.status!=200:raise OSError('Internet preflight failed')
                last_error=None;break
            except OSError as exc:
                last_error=exc
                time.sleep(2)
        if last_error is not None:raise last_error
        connected=True
        report.update(success=True,hotspot_ip=address,internet_verified=True)
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
        if original:
            try:connect(original);report['rollback_requested']=True
            except OSError:report['rollback_requested']=False
    finally:
        if created and not connected:dll.WlanDeleteProfile(handle,C.byref(guid),profile,None)
        dll.WlanCloseHandle(handle,None)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if connected else 1


if __name__=='__main__':raise SystemExit(main())
