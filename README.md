# Script para subir máquinas — rede 10.42

Instala e configura de 1 a 2 servidores Debian 11 na faixa `10.42.0.200`–`10.42.0.254/24`, com gateway `10.42.0.1` e interface `eth1`.

Leia o [manual de uso](LEIA-ME.txt) antes de executar. No Mint, instale `python3-paramiko` e `iputils-ping`, extraia os arquivos juntos e rode `python3 subir-maquinas.py` como usuário normal.

Depois de confirmar a rede após o reboot, o instalador atualiza/instala o verificador [teste_saude_ssd](https://github.com/Lucasuimaraes/teste_saude_ssd) e executa o **modo consulta**, sem testes intencionais de carga. Ele mostra o progresso no terminal, pede os discos SATA inteiros a conferir e transfere os relatórios para `~/Relatorios-validacao-servidor/<execução>/<IP>/` no Mint. O relatório não é enviado ao GitHub.

A sondagem de IPs sem resposta não garante disponibilidade. Reserve os endereços no DHCP/inventário. O modo consulta fornece evidências para revisão técnica; não certifica sozinho a saúde do servidor.
