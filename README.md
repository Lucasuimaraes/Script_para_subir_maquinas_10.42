# Subir máquinas Debian 11 — rede 10.42

Copie o comando abaixo no Terminal do Linux Mint. Ele baixa o instalador direto do GitHub, abre uma nova janela de Terminal e inicia as perguntas para configurar 1 ou 2 máquinas. Não precisa baixar/extrair ZIP nem entrar em uma pasta específica. Execute como usuário normal, sem `sudo`.

```bash
python3 -c "import urllib.request as u; open('/tmp/ironvox-10.42.sh','wb').write(u.urlopen('https://raw.githubusercontent.com/Lucasuimaraes/Script_para_subir_maquinas_10.42/main/instalar.sh').read())" && (x-terminal-emulator -e bash /tmp/ironvox-10.42.sh || bash /tmp/ironvox-10.42.sh)
```

O instalador pedirá a senha do computador para instalar os requisitos e, em seguida, apresentará a pergunta:

```text
Quantas máquinas deseja configurar? [1 ou 2]:
```

Depois, informe o IP atual de cada Debian, a senha root quando solicitada e escolha IPs finais que estejam reservados para essas máquinas. A lista de IPs sem resposta não garante que estejam livres.

Após mudar a rede e confirmar acesso pelos novos IPs, o programa também executa a validação de saúde em modo consulta, mostra a execução no Terminal e salva os relatórios em `~/Relatorios-validacao-servidor/`. A validação não realiza testes de carga.
Ao terminar os testes, o programa abre uma janela de Terminal conectada como root para cada máquina configurada. Se forem duas, abre duas janelas.

O projeto fica instalado em `~/.local/share/ironvox/Script_para_subir_maquinas_10.42` e será atualizado automaticamente nas próximas execuções.
