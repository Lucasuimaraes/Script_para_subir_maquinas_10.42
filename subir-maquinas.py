#!/usr/bin/env python3
"""Instalador interativo IRONVOX para Linux Mint. Executar como usuário normal."""
import concurrent.futures, getpass, hashlib, base64, ipaddress, json, os, pathlib, re, shlex, shutil, socket, subprocess, sys, time
try:
    import paramiko
except ImportError:
    sys.exit('Instale a dependência no Mint: sudo apt install python3-paramiko iputils-ping')
BASE = pathlib.Path(__file__).resolve().parent

def ask_ip(prompt, network=None):
    while True:
        try:
            value = str(ipaddress.IPv4Address(input(prompt).strip()))
            if network and ipaddress.ip_address(value) not in ipaddress.ip_network(network):
                raise ValueError()
            return value
        except ValueError:
            print('Informe um IPv4 válido' + (' na rede ' + network if network else '') + '.')

class Trust(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        fingerprint = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        print(f'\nChave SSH de {hostname}: {key.get_name()} SHA256:{fingerprint}')
        if input('Confirme a identidade da máquina. Digite ACEITAR: ').strip() != 'ACEITAR':
            raise RuntimeError('Chave não aceita.')
        client.get_host_keys().add(hostname, key.get_name(), key)


def connect(ip, password, key=None):
    c = paramiko.SSHClient()
    if key is None:
        c.load_system_host_keys()
        c.set_missing_host_key_policy(Trust())
    else:
        c.get_host_keys().add(ip, key.get_name(), key)
        c.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        c.connect(ip, username='root', password=password, timeout=8, auth_timeout=12,
                  banner_timeout=12, allow_agent=False, look_for_keys=False)
        c.get_transport().set_keepalive(15)
        return c
    except BaseException:
        c.close()
        raise


def execute(client, command, echo=False, timeout=1800):
    channel = client.get_transport().open_session(timeout=15)
    channel.set_combine_stderr(True)
    channel.exec_command(command)
    data = bytearray()
    start = time.monotonic()
    while True:
        if channel.recv_ready():
            chunk = channel.recv(65536)
            data.extend(chunk)
            if echo:
                print(chunk.decode(errors='replace'), end='', flush=True)
        elif channel.exit_status_ready():
            break
        else:
            if time.monotonic() - start > timeout:
                channel.close()
                raise RuntimeError('Tempo limite no comando remoto. Verifique a máquina antes de repetir.')
            time.sleep(0.1)
    status = channel.recv_exit_status()
    channel.close()
    output = data.decode(errors='replace')
    if status != 0:
        raise RuntimeError(f'Comando remoto falhou ({status}):\n{output[-5000:]}')
    return output


def responds(ip):
    p = subprocess.run(['ping', '-n', '-c', '1', '-W', '1', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if p.returncode == 0:
        return True
    if p.returncode != 1:
        raise RuntimeError('Falha ao executar ping; não é possível interpretar a sondagem.')
    for port in [22, 80, 443]:
        try:
            with socket.create_connection((ip, port), timeout=0.35):
                return True
        except ConnectionRefusedError:
            return True
        except (TimeoutError, OSError):
            pass
    return False


def select_health_disks(client):
    print('Discos detectados na máquina:')
    execute(client, 'lsblk -d -o NAME,MODEL,SIZE,TYPE', echo=True, timeout=30)
    raw_disks = execute(client, 'lsblk -dnpo NAME,TYPE', timeout=30)
    available = []
    for line in raw_disks.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == 'disk' and re.fullmatch(r'/dev/sd[a-z]+', parts[0]):
            available.append(parts[0])
    if not available:
        raise RuntimeError('Nenhum disco SATA inteiro /dev/sdX foi detectado; não iniciei a validação.')
    default = '/dev/sda' if '/dev/sda' in available else ''
    print('Discos SATA disponíveis para o teste:', ', '.join(available))
    while True:
        prompt = 'Discos inteiros para validar, separados por espaço'
        if default:
            prompt += f' [Enter usa {default}]'
        value = input(prompt + ': ').strip()
        disks = value.replace(',', ' ').split() if value else ([default] if default else [])
        if disks and len(disks) == len(set(disks)) and all(disk in available for disk in disks):
            return disks
        print('Informe um ou mais discos da lista, por exemplo: /dev/sda /dev/sdb')


def validate_server_health(ip, password, key, report_root):
    print(f'\n=== Validação de saúde em {ip} (modo consulta, sem stress) ===', flush=True)
    client = None
    try:
        client = connect(ip, password, key)
        setup = '''set -eu
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git ca-certificates python3
if [ -d /opt/teste_saude_ssd/.git ]; then
    git -C /opt/teste_saude_ssd pull --ff-only
elif [ -e /opt/teste_saude_ssd ]; then
    echo 'ERRO: /opt/teste_saude_ssd existe, mas não é um clone Git; revise antes de continuar.' >&2
    exit 1
else
    git clone --branch master https://github.com/Lucasuimaraes/teste_saude_ssd.git /opt/teste_saude_ssd
fi
bash /opt/teste_saude_ssd/validacao-servidor/instalar.sh
validar-servidor --instalar-dependencias
validar-servidor --versao
'''
        execute(client, setup, echo=True, timeout=3600)
        disks = select_health_disks(client)
        args = ' '.join('--disco ' + shlex.quote(disk) for disk in disks)
        command = ('set +e; validar-servidor --modo consulta --perfil auto ' + args +
                   '; result=$?; printf "\nIRONVOX_VALIDATION_EXIT=%s\n" "$result"; exit 0')
        output = execute(client, command, echo=True, timeout=3600)
        match = re.search(r'(?m)^IRONVOX_VALIDATION_EXIT=(\d+)$', output)
        if not match:
            raise RuntimeError('A validação não retornou o código final esperado.')
        result_code = int(match.group(1))
        report_match = re.search(r'(?m)^Relatórios salvos em:\s*(\S+)\s*$', output)
        if not report_match:
            raise RuntimeError('A validação não informou a pasta dos relatórios.')
        remote_dir = report_match.group(1)
        local_dir = report_root / ip
        local_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        local_dir.chmod(0o700)
        saved = []
        with client.open_sftp() as sftp:
            for filename in ('DIAGNOSTICO.txt', 'RESUMO.txt', 'RELATORIO_COMPLETO.txt'):
                remote_file = remote_dir + '/' + filename
                local_file = local_dir / filename
                sftp.get(remote_file, str(local_file))
                local_file.chmod(0o600)
                saved.append(local_file)
        diagnosis = local_dir / 'DIAGNOSTICO.txt'
        if result_code == 0:
            print(f'Validação concluída sem alertas automáticos em {ip}; ainda exige revisão técnica.')
        elif result_code == 1:
            print(f'Validação em {ip} encontrou pendências/falhas para revisão; relatórios copiados.')
        else:
            print(f'Validação em {ip} terminou com código {result_code}; confira o relatório/inconclusão.')
        for path in saved:
            print('Relatório local:', path)
        return {'ip': ip, 'code': result_code, 'diagnosis': diagnosis}
    except Exception as exc:
        print(f'FALHA na validação de saúde de {ip}: {exc}', file=sys.stderr)
        return {'ip': ip, 'code': None, 'diagnosis': None}
    finally:
        if client is not None:
            client.close()


def main():
    if not (BASE / 'ironvox-remoto.py').exists():
        raise RuntimeError('Mantenha ironvox-remoto.py na mesma pasta deste arquivo.')
    print('IRONVOX — Debian 11 / usuário root / mesma placa de rede')
    while True:
        qty = input('Quantas máquinas deseja configurar? [1 ou 2]: ').strip()
        if qty in ['1', '2']:
            break
    ips = []
    while len(ips) < int(qty):
        ip = ask_ip(f'IP atual da máquina {len(ips)+1}: ')
        if ip not in ips:
            ips.append(ip)
        else:
            print('IP repetido.')
    password = getpass.getpass('Senha root das máquinas (não será gravada): ')
    print('Sondando 10.42.0.200–254 a partir do Mint...')
    pool = [f'10.42.0.{n}' for n in range(200, 255)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        candidates = [ip for ip, busy in zip(pool, executor.map(responds, pool)) if not busy and ip not in ips]
    if len(candidates) < len(ips):
        raise RuntimeError('Não foram encontrados candidatos suficientes.')
    print('Candidatos sem resposta (não são garantia de IP livre): ' + ', '.join(candidates))
    print('Consulte o DHCP/inventário. Reserve os IPs para estes equipamentos antes de prosseguir.')
    destinations = []
    for old in ips:
        default = next(ip for ip in candidates if ip not in destinations)
        while True:
            chosen = input(f'Novo IP para {old} [{default}]: ').strip() or default
            if chosen in candidates and chosen not in destinations:
                destinations.append(chosen)
                break
            print('Escolha um dos candidatos ainda não utilizados.')
    print('\nPlano:')
    for old, new in zip(ips, destinations):
        print(f'  {old} → {new}/24, interface eth1, gateway 10.42.0.1')
    print('O script instalará pacotes, alterará aliases, GRUB e rede, e reiniciará cada máquina.')
    print('Após validar o novo IP, instalará o verificador teste_saude_ssd e rodará o modo consulta (sem stress). Os relatórios serão copiados para o Mint.')
    if input('Os IPs estão reservados fora do DHCP e posso aplicar? Digite CONFIGURAR: ').strip() != 'CONFIGURAR':
        print('Cancelado sem acessar as máquinas.')
        return
    completed = []
    health_results = []
    report_root = pathlib.Path.home() / 'Relatorios-validacao-servidor' / time.strftime('%Y%m%d-%H%M%S')
    for old, new in zip(ips, destinations):
        print(f'\n=== Configurando {old} → {new} ===', flush=True)
        c = connect(old, password)
        key = c.get_transport().get_remote_server_key()
        try:
            execute(c, '. /etc/os-release; test "$ID" = debian && test "$VERSION_ID" = 11', timeout=30)
            execute(c, 'command -v python3 >/dev/null || (apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3)', echo=True)
            with c.open_sftp() as sftp:
                remote = '/root/ironvox-installer.py'
                sftp.put(str(BASE / 'ironvox-remoto.py'), remote)
                sftp.chmod(remote, 0o700)
            info = json.loads(execute(c, f'python3 {remote} inspect {shlex.quote(old)}'))
            print('Placa identificada:', info['interface'], 'MAC:', info['mac'])
            if responds(new):
                raise RuntimeError('O IP escolhido passou a responder; abortando.')
            output = execute(c, f'python3 {remote} apply {shlex.quote(old)} {shlex.quote(new)}', echo=True)
            if 'PRONTO_REINICIAR' not in output:
                raise RuntimeError('Preparação não confirmada.')
            before = execute(c, 'cat /proc/sys/kernel/random/boot_id').strip()
            execute(c, 'systemd-run --unit=ironvox-reboot --on-active=3s /sbin/reboot')
        finally:
            c.close()
        print('Reinicialização agendada. Aguardando 60 segundos...', flush=True)
        time.sleep(60)
        deadline = time.monotonic() + 170
        success = False
        last_error = ''
        while time.monotonic() < deadline:
            client = None
            try:
                client = connect(new, password, key)
                boot = execute(client, 'cat /proc/sys/kernel/random/boot_id', timeout=20).strip()
                if boot == before:
                    raise RuntimeError('Reinicialização ainda não ocorreu.')
                actual_mac = execute(client, 'cat /sys/class/net/eth1/address', timeout=20).strip()
                if actual_mac != info['mac']:
                    raise RuntimeError('MAC de eth1 não corresponde à placa original.')
                addresses = json.loads(execute(client, 'ip -j -4 addr show dev eth1', timeout=20))
                if not any(a.get('local') == new and a.get('prefixlen') == 24 for d in addresses for a in d.get('addr_info', [])):
                    raise RuntimeError('IP/prefixo não confirmado.')
                routes = json.loads(execute(client, 'ip -j -4 route show default', timeout=20))
                if not any(r.get('gateway') == '10.42.0.1' and r.get('dev') == 'eth1' for r in routes):
                    raise RuntimeError('Gateway não confirmado.')
                execute(client, 'arping -I eth1 -c 2 -w 4 10.42.0.1', timeout=15)
                execute(client, 'getent ahostsv4 deb.debian.org', timeout=20)
                execute(client, 'systemctl disable --now ironvox-rollback.service && rm /etc/systemd/system/ironvox-rollback.service && systemctl daemon-reload', timeout=30)
                print(f'SUCESSO: {new} — SSH, MAC, IP, gateway e resolução DNS verificados.')
                completed.append(new)
                success = True
                break
            except Exception as exc:
                last_error = str(exc)
            finally:
                if client is not None:
                    client.close()
            time.sleep(5)
        if not success:
            raise RuntimeError(f'Não foi possível validar {new}: {last_error}\nA recuperação tentará restaurar a rede anterior aos 5 minutos de boot.\nAguarde o segundo reboot e tente o IP anterior {old}. Se era DHCP, consulte a nova concessão ou o console.\nAs demais máquinas não serão alteradas. Concluídas: {completed}')
        health_results.append(validate_server_health(new, password, key, report_root))
    print('\nConcluído. Acesso pelo terminal do Mint:')
    for ip in completed:
        print('  ssh root@' + ip)
    if health_results:
        print('\nRelatórios de saúde no Mint:')
        for result in health_results:
            if result['diagnosis']:
                print('  ' + str(result['diagnosis']))
        if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            if shutil.which('xdg-open'):
                for result in health_results:
                    if result['diagnosis']:
                        subprocess.Popen(['xdg-open', str(result['diagnosis'])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                print('Abrindo os diagnósticos na interface gráfica do Mint.')

if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('\nINTERROMPIDO:', str(exc) or 'Cancelado pelo usuário.', file=sys.stderr)
        sys.exit(1)
