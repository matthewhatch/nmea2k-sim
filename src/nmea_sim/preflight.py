"""Read-only SocketCAN checks. Never opens a CAN socket or changes a link.

A successful report covers software settings only; it cannot approve wiring,
identity assignment, isolation, certification or an operational vessel network.
"""
import json
import subprocess
from .config import Config, parse_config


def evaluate_link(config: Config, link: dict) -> dict:
    checks = []
    def check(name, passed, detail):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})
    kind = link.get('linkinfo', {}).get('info_kind')
    check('interface', link.get('ifname') == config.channel, 'selected interface must match the inspected link')
    check('type', kind in ('vcan', 'can'), 'kernel kind must be vcan or can')
    check('up', 'UP' in link.get('flags', []), 'interface must already be UP; this command does not configure it')
    if kind == 'can':
        data = link.get('linkinfo', {}).get('info_data', {})
        check('bitrate', data.get('bittiming', {}).get('bitrate') == 250000, 'physical bench CAN requires 250000 bit/s')
        check('controller_state', data.get('state') == 'ERROR-ACTIVE', 'controller must be ERROR-ACTIVE')
        # iproute2 omits ctrlmode when all mode flags are zero (normal mode).
        # Explicit null or a different schema is still unverified.
        modes = data.get('ctrlmode', [])
        check('mode_known', isinstance(modes, list), 'iproute2 must expose controller modes as a list')
        allowed = {'BERR-REPORTING', 'TRIPLE-SAMPLING', 'CC-LEN8-DLC'}
        check('normal_classic_mode', isinstance(modes, list) and all(mode in allowed for mode in modes),
              'normal classic CAN mode; reject listen-only, loopback, FD, one-shot and unknown flags')
        check('physical_opt_in', config.allow_physical_tx, '--allow-physical-tx remains required by the simulator')
        check('assigned_identity', config.manufacturer_code != 2046,
              '2046 is virtual-test-only; other assignments still require operator evidence')
    manual = [] if kind == 'vcan' else [
        'isolated bench with no live engine or operational vessel connection',
        'board revision, jumpers, driver, connector pinout and isolation verified',
        'fused power, voltage, grounding and two-end termination measured',
        'manufacturer identity assignment and source/NAME uniqueness documented',
        'hardware and display acceptance captures reviewed',
    ]
    return {'channel': config.channel, 'interface_kind': kind,
            'software_checks_passed': all(item['passed'] for item in checks),
            'checks': checks, 'unverified_manual_gates': manual,
            'transmission_authorized': False,
            'note': 'Read-only report. Passing software checks never authorizes physical transmission.'}


def main(argv=None):
    config = parse_config(argv)
    try:
        result = subprocess.run(['ip', '-json', '-details', 'link', 'show', 'dev', config.channel],
                                check=True, capture_output=True, text=True, timeout=3)
        links = json.loads(result.stdout)
        if not isinstance(links, list) or len(links) != 1 or not isinstance(links[0], dict):
            raise ValueError('expected exactly one interface record')
        report = evaluate_link(config, links[0])
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps({'channel': config.channel, 'software_checks_passed': False,
                          'transmission_authorized': False, 'error': str(exc)}), flush=True)
        return 2
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['software_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
