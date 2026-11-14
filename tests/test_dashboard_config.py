import pytest
from nmea_sim.dashboard_config import parse_dashboard_config


def test_channel_default_environment_and_cli(monkeypatch):
    monkeypatch.delenv('NMEA_CAN_CHANNEL', raising=False)
    assert parse_dashboard_config([]).channel == 'vcan0'
    monkeypatch.setenv('NMEA_CAN_CHANNEL', 'can0')
    assert parse_dashboard_config([]).channel == 'can0'
    assert parse_dashboard_config(['--channel', 'vcan0']).channel == 'vcan0'


@pytest.mark.parametrize('args', [['--channel', ''], ['--channel', '../can0'],
    ['--stale-after', '0'], ['--stale-after', 'nan'], ['--quit-after', '-1'],
    ['--source-address', '252'], ['--engine-instance', '253'], ['--screenshot', 'test.png']])
def test_invalid_dashboard_arguments(args):
    with pytest.raises(SystemExit):
        parse_dashboard_config(args)


def test_headless_and_missing_x11_library_errors(monkeypatch):
    from nmea_sim.dashboard import platform_error
    assert 'desktop session' in platform_error({})
    assert platform_error({'QT_QPA_PLATFORM': 'offscreen'}) is None
    def missing(_):
        raise OSError('library missing')
    monkeypatch.setattr('ctypes.CDLL', missing)
    assert 'libxcb-cursor0' in platform_error({'DISPLAY': ':42'})
    assert platform_error({'WAYLAND_DISPLAY': 'wayland-0'}) is None



def test_default_renderer_matches_verified_software_backend():
    from nmea_sim.dashboard import configure_rendering
    settings = {}
    configure_rendering(settings)
    assert settings['QT_QUICK_BACKEND'] == 'software'
    settings = {'QT_QUICK_BACKEND': 'rhi'}
    configure_rendering(settings)
    assert settings['QT_QUICK_BACKEND'] == 'rhi'
