from dataclasses import replace
from types import SimpleNamespace
import copy
import json
import pytest
from nmea_sim.config import Config
from nmea_sim.preflight import evaluate_link, main

# Synthetic read-only fixture; never opens or transmits on a physical interface.
PHYSICAL = {'ifname': 'can0', 'flags': ['UP'], 'linkinfo': {'info_kind': 'can',
    'info_data': {'state': 'ERROR-ACTIVE', 'bittiming': {'bitrate': 250000}, 'ctrlmode': []}}}


def test_virtual_report():
    report = evaluate_link(Config('bench0', 35), {'ifname': 'bench0', 'flags': ['UP'],
                          'linkinfo': {'info_kind': 'vcan'}})
    assert report['software_checks_passed']
    assert report['transmission_authorized'] is False
    assert report['unverified_manual_gates'] == []


def test_physical_default_identity_and_optin_fail():
    report = evaluate_link(Config('can0', 35), PHYSICAL)
    assert not report['software_checks_passed']
    failed = {item['name'] for item in report['checks'] if not item['passed']}
    assert failed == {'physical_opt_in', 'assigned_identity'}


def test_configuration_only_software_check_does_not_approve_hardware():
    report = evaluate_link(Config('can0', 35, allow_physical_tx=True, manufacturer_code=123), PHYSICAL)
    assert report['software_checks_passed']
    assert report['unverified_manual_gates']
    assert not report['transmission_authorized']


@pytest.mark.parametrize('state', ['BUS-OFF', 'ERROR-PASSIVE', 'STOPPED', None])
def test_bad_controller_state(state):
    link = copy.deepcopy(PHYSICAL)
    link['linkinfo']['info_data']['state'] = state
    assert not evaluate_link(Config('can0', 35, True, manufacturer_code=123), link)['software_checks_passed']


@pytest.mark.parametrize('mode', ['LISTEN-ONLY', 'LOOPBACK', 'FD', 'PRESUME-ACK'])
def test_prohibited_modes(mode):
    link = copy.deepcopy(PHYSICAL)
    link['linkinfo']['info_data']['ctrlmode'] = [mode]
    assert not evaluate_link(Config('can0', 35, True, manufacturer_code=123), link)['software_checks_passed']


def test_wrong_bitrate_and_unknown_modes():
    link = copy.deepcopy(PHYSICAL)
    link['linkinfo']['info_data']['bittiming']['bitrate'] = 500000
    link['linkinfo']['info_data']['ctrlmode'] = None
    report = evaluate_link(Config('can0', 35, True, manufacturer_code=123), link)
    assert not report['software_checks_passed']


def test_preflight_only_reads_ip_json(monkeypatch, capsys):
    def run(args, **kwargs):
        assert args == ['ip', '-json', '-details', 'link', 'show', 'dev', 'can0']
        return SimpleNamespace(stdout=json.dumps([PHYSICAL]))
    monkeypatch.setattr('subprocess.run', run)
    monkeypatch.setattr('can.Bus', lambda **kw: pytest.fail('preflight must never open a socket'))
    assert main(['--channel', 'can0']) == 1
    assert json.loads(capsys.readouterr().out)['transmission_authorized'] is False


def test_iproute_zero_flags_omits_ctrlmode():
    link = copy.deepcopy(PHYSICAL)
    del link['linkinfo']['info_data']['ctrlmode']
    assert evaluate_link(Config('can0', 35, True, manufacturer_code=123), link)['software_checks_passed']
