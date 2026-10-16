# Script para subir máquinas — rede 10.42

Configure de 1 a 2 máquinas Debian 11 na faixa `10.42.0.200`–`10.42.0.254/24`, com gateway `10.42.0.1` e interface `eth1`.

## Instalar e abrir

No Linux Mint, copie e cole este único comando no Terminal. Ele funciona de qualquer diretório e não precisa de extração manual:

```bash
python3 -c 'import os, subprocess, tempfile, urllib.request; url="https://raw.githubusercontent.com/Lucasuimaraes/Script_para_subir_maquinas_10.42/main/instalar.sh"; f=tempfile.NamedTemporaryFile(prefix="ironvox-", suffix=".sh", delete=False); f.write(urllib.request.urlopen(url, timeout=30).read()); f.close(); result=subprocess.run(["bash", f.name]).returncode; os.unlink(f.name); raise SystemExit(result)'
```

O instalador pede sua senha de `sudo` para instalar `git`, certificados, Python, Paramiko e `ping`; depois baixa ou atualiza o projeto em `~/.local/share/ironvox/Script_para_subir_maquinas_10.42` (ou em `$XDG_DATA_HOME/ironvox/Script_para_subir_maquinas_10.42`) e abre o instalador interativo no mesmo Terminal. Execute como usuário normal, sem `sudo`.

## O que acontece depois

O instalador configura a rede após confirmar os IPs reservados e validar o acesso pelo novo endereço. Em seguida, instala/atualiza [teste_saude_ssd](https://github.com/Lucasuimaraes/teste_saude_ssd) e executa a validação em **modo consulta**, sem testes de carga. Mostra o progresso no Terminal, pede quais discos SATA inteiros verificar e copia os relatórios para `~/Relatorios-validacao-servidor/<execução>/<IP>/` no Mint. Tenta abrir o diagnóstico na interface gráfica. Os relatórios ficam locais e não são enviados ao GitHub.

A sondagem de IPs que não responderam não garante disponibilidade; confirme e reserve endereços no DHCP/inventário. O modo consulta fornece evidências para revisão técnica, não um certificado de aprovação.

Manual detalhado/fallback: [LEIA-ME.txt](LEIA-ME.txt). O lançador está em [instalar.sh](instalar.sh).
