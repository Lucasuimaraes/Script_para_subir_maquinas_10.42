#!/usr/bin/env python3
"""Executado no Debian pelo instalador. Não executar manualmente."""
import glob, ipaddress, json, os, pathlib, re, shutil, subprocess, sys, time
P = pathlib.Path

def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

def prepare_repository_network(dev):
    """Ensure the intended gateway and Debian DNS work before touching packages."""
    routes = json.loads(run('ip', '-j', '-4', 'route', 'show', 'default'))
    if len(routes) > 1:
        raise RuntimeError('Há várias rotas padrão; não é seguro escolher uma automaticamente.')
    current = routes[0] if routes else None
    if current and current.get('dev') != dev:
        raise RuntimeError('A rota padrão usa ' + str(current.get('dev')) + ', mas o SSH chegou por ' + dev + '.')
    gateway = '10.42.0.1'
    if not current or current.get('gateway') != gateway:
        print('Rota padrão atual: ' + str(current or 'ausente'), flush=True)
        print('Testando gateway esperado ' + gateway + ' pela ' + dev + '.', flush=True)
        # The target gateway is directly on the configured /24. Set the
        # temporary route before DNS/APT, then write it persistently later.
        run('ip', 'route', 'replace', 'default', 'via', gateway, 'dev', dev)
        print('Rota temporária definida para ' + gateway + '.', flush=True)
    try:
        dns = run('getent', 'ahostsv4', 'deb.debian.org')
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('A rede ainda não resolve deb.debian.org pela rota ' + gateway + '. Verifique gateway e DNS antes de continuar.\n' + (exc.output or ''))
    if not dns.strip():
        raise RuntimeError('DNS não retornou endereços IPv4 para deb.debian.org.')
    print('DNS de deb.debian.org validado.', flush=True)

def update_package_indexes():
    result = subprocess.run(['apt-get', 'update'], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end='', flush=True)
    if result.returncode != 0 or re.search(r'(?m)^(?:Err:|W:)', result.stdout):
        raise RuntimeError('APT não atualizou todos os índices. Confira rede/DNS; nenhum pacote será instalado.')

def inspect(old):
    osinfo = P('/etc/os-release').read_text()
    if 'ID=debian' not in osinfo or 'VERSION_ID="11"' not in osinfo:
        raise RuntimeError('Este instalador exige Debian 11.')
    devices = json.loads(run('ip', '-j', '-4', 'addr'))
    matches = [d for d in devices if any(a.get('local') == old for a in d.get('addr_info', []))]
    if len(matches) != 1:
        raise RuntimeError('Não foi possível identificar a placa pelo IP SSH.')
    dev = matches[0]['ifname']
    physical = [p.name for p in P('/sys/class/net').iterdir() if (p / 'device').exists()]
    if dev not in physical:
        raise RuntimeError('Bridge, bond ou placa virtual: configuração exige análise manual.')
    if len(physical) > 1 and dev != 'eth1':
        raise RuntimeError('Há várias placas e a placa atual não é eth1. Não é seguro presumir sua ordem após alterar o GRUB.')
    if len(physical) > 1 and not all(re.fullmatch(r'eth\d+', n) for n in physical):
        raise RuntimeError('Nomes mistos de placas: revisar mapeamento antes da automação.')
    for service in ['NetworkManager', 'systemd-networkd']:
        if subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0:
            raise RuntimeError(service + ' ativo: este script exige ifupdown.')
    files = [P('/etc/network/interfaces')] + [P(x) for x in glob.glob('/etc/network/interfaces.d/*') if P(x).is_file()]
    for f in files:
        for line in f.read_text().splitlines():
            s = line.strip()
            if s.startswith('iface ') and s.split()[1] not in ['lo', dev]:
                configured = s.split()[1]
                # A configuração antiga pode ainda citar o nome previsível
                # (por exemplo enp0s25) embora o GRUB já tenha renomeado a
                # placa para eth1. Permita removê-la apenas se não existir
                # como interface atual; a configuração inteira é copiada
                # para o backup antes de ser substituída.
                stale_predictable = (not (P('/sys/class/net') / configured).exists()
                                     and re.fullmatch(r'(?:en|wl|ww|ib)[a-zA-Z0-9_.:-]+', configured))
                if not stale_predictable:
                    raise RuntimeError('Outra interface configurada em ' + str(f))
            if s.startswith(('pre-up ', 'post-up ', 'up ', 'down ', 'pre-down ', 'post-down ', 'mapping ', 'rename ')):
                raise RuntimeError('Configuração personalizada em ' + str(f))
            if s.startswith(('source ', 'source-directory ')) and s not in ['source /etc/network/interfaces.d/*', 'source-directory /etc/network/interfaces.d']:
                raise RuntimeError('Inclusão de rede personalizada: ' + s)
    # Pacotes Debian podem deixar arquivos inertes apenas com comentários em
    # grub.d (notavelmente init-select.cfg). Eles não definem opções e podem
    # ser mantidos. Só configurações executáveis/atribuições exigem revisão.
    for grub_fragment in glob.glob('/etc/default/grub.d/*'):
        fragment = P(grub_fragment)
        if fragment.is_file() and any(line.strip() and not line.lstrip().startswith('#')
                                      for line in fragment.read_text().splitlines()):
            raise RuntimeError('Existe configuração ativa em grub.d (' + str(fragment) + '); revisar antes de automatizar.')
    if P('/etc/systemd/system/ironvox-rollback.service').exists():
        raise RuntimeError('Há uma recuperação anterior pendente.')
    return {'interface': dev, 'mac': P('/sys/class/net/' + dev + '/address').read_text().strip(), 'physical': physical}

mode, old = sys.argv[1:3]
if mode == 'inspect':
    print(json.dumps(inspect(old)))
elif mode == 'apply':
    new = str(ipaddress.IPv4Address(sys.argv[3]))
    if not 200 <= int(new.split('.')[-1]) <= 254 or not new.startswith('10.42.0.'):
        raise RuntimeError('IP fora da faixa permitida.')
    info = inspect(old)
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    print('Verificando gateway e DNS antes do APT...', flush=True)
    prepare_repository_network(info['interface'])
    update_package_indexes()
    print('Instalando pacotes básicos...', flush=True)
    subprocess.run(['apt-get', 'install', '-y', 'net-tools', 'nano'], check=True)
    print('Instalando ferramentas e verificadores de rede...', flush=True)
    subprocess.run(['apt-get', 'install', '-y', 'mtr', 'nmap', 'hdparm', 'htop', 'atop', 'iftop', 'smartmontools', 'telnet', 'git', 'tcpdump', 'lm-sensors', 'bc', 'traceroute', 'hddtemp', 'ethtool', 'iputils-arping'], check=True)
    if not shutil.which('arping'):
        raise RuntimeError('O pacote iputils-arping foi solicitado, mas o comando arping não ficou disponível.')
    print('Testando o gateway e o IP escolhido por ARP...', flush=True)
    print(run('ethtool', '-i', info['interface']))
    # ARP precisa alcançar diretamente a rede final pela mesma placa.
    subprocess.run(['arping', '-I', info['interface'], '-c', '2', '-w', '4', '10.42.0.1'], check=True)
    subprocess.run(['arping', '-D', '-I', info['interface'], '-c', '3', '-w', '5', new], check=True)
    backup = P('/root/ironvox-backup-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700)
    paths = ['/etc/network/interfaces', '/etc/network/interfaces.d', '/etc/default/grub', '/root/.bashrc', '/etc/resolv.conf', '/etc/udev/rules.d/70-ironvox-net.rules']
    manifest = []
    for index, name in enumerate(paths):
        src = P(name)
        exists = os.path.lexists(name)
        manifest.append((name, exists, str(index)))
        if exists:
            subprocess.run(['cp', '-a', name, str(backup / str(index))], check=True)
    (backup / 'manifest.json').write_text(json.dumps(manifest))
    restore = '''#!/usr/bin/python3
import json, pathlib, subprocess, os, shutil
b = pathlib.Path(__file__).parent
for name, existed, index in json.loads((b / 'manifest.json').read_text()):
    p = pathlib.Path(name)
    if p.is_dir() and not p.is_symlink(): shutil.rmtree(p)
    elif os.path.lexists(name): p.unlink()
    if existed: subprocess.run(['cp', '-a', str(b / index), name], check=True)
subprocess.run(['update-grub'], check=True)
subprocess.run(['update-initramfs', '-u'], check=True)
subprocess.run(['systemctl', 'disable', 'ironvox-rollback.service'])
pathlib.Path('/etc/systemd/system/ironvox-rollback.service').unlink(missing_ok=True)
subprocess.run(['systemctl', 'daemon-reload'])
if '--reboot' in __import__('sys').argv: subprocess.run(['systemctl', 'reboot'])
'''
    (backup / 'restore.py').write_text(restore)
    print('BACKUP=' + str(backup), flush=True)
    try:
        bash = P('/root/.bashrc')
        content = bash.read_text() if bash.exists() else ''
        content = re.sub(r'(?m)^(\s*)#\s*(alias\s+.+)$', r'\1\2', content)
        for name, val in [('ll', 'ls -alF'), ('ls', 'ls --color=auto'), ('cp', 'cp -i'), ('rm', 'rm -i'), ('mv', 'mv -i')]:
            if not re.search(r'(?m)^\s*alias\s+' + name + '=', content):
                content += '\nalias ' + name + "='" + val + "'\n"
        bash.write_text(content.replace('\r\n', '\n').replace('\r', ''))
        subprocess.run(['bash', '-n', str(bash)], check=True)
        grub = P('/etc/default/grub')
        content = grub.read_text()
        match = re.findall(r'^GRUB_CMDLINE_LINUX="([^"\n]*)"\s*$', content, re.M)
        if len(match) != 1 or any(c in match[0] for c in '$`\\'):
            raise RuntimeError('GRUB_CMDLINE_LINUX não está no formato simples esperado.')
        args = [a for a in match[0].split() if not a.startswith(('net.ifnames=', 'biosdevname='))]
        args += ['net.ifnames=0', 'biosdevname=0']
        grub.write_text(re.sub(r'^GRUB_CMDLINE_LINUX="[^"\n]*"\s*$', 'GRUB_CMDLINE_LINUX="' + ' '.join(args) + '"', content, flags=re.M))
        # Com uma única placa, eth1 não colide com outro nome do kernel.
        if len(info['physical']) == 1:
            P('/etc/udev/rules.d/70-ironvox-net.rules').write_text('SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="' + info['mac'] + '", NAME="eth1"\n')
        dns = P('/etc/resolv.conf').read_text()
        if not re.search(r'^nameserver\s+(?!127\.|::1)', dns, re.M):
            raise RuntimeError('DNS atual é local ou ausente; configurar DNS antes de continuar.')
        resolver = P('/etc/resolv.conf')
        if resolver.is_symlink(): resolver.unlink()
        resolver.write_text(dns)
        folder = P('/etc/network/interfaces.d')
        folder.mkdir(exist_ok=True)
        for f in folder.iterdir():
            if f.is_file() or f.is_symlink(): f.unlink()
        P('/etc/network/interfaces').write_text('auto lo\niface lo inet loopback\n\nsource /etc/network/interfaces.d/*\n')
        (folder / 'eth1').write_text('auto eth1\niface eth1 inet static\n    address ' + new + '/24\n    gateway 10.42.0.1\n')
        run('ifquery', 'eth1')
        run('update-grub')
        run('update-initramfs', '-u')
        unit = '[Unit]\nDescription=Recuperacao automatica IRONVOX\nAfter=local-fs.target\n\n[Service]\nType=simple\nExecStart=/bin/sh -c "sleep 300; /usr/bin/python3 ' + str(backup / 'restore.py') + ' --reboot"\n\n[Install]\nWantedBy=multi-user.target\n'
        P('/etc/systemd/system/ironvox-rollback.service').write_text(unit)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'enable', 'ironvox-rollback.service')
        print('PRONTO_REINICIAR ' + info['mac'], flush=True)
    except BaseException:
        subprocess.run(['python3', str(backup / 'restore.py')], check=False)
        raise
