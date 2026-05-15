import PyInstaller.__main__
import shutil
import os

PyInstaller.__main__.run([
    'main.py',
    '--name=Importador_Sistec',
    '--onedir',
    '--noconsole',
    '--clean',
    '--noconfirm',
    '--icon=icon.ico',
    '--add-data=icon.ico;.',
    '--add-data=sistec.jpg;.',
    '--add-data=Icone_plano.jpg;.',
    '--add-data=nfe_cli.jpg;.',
    '--add-binary=fbclient_*.dll;.'
])

# --- PÓS-COMPILAÇÃO: ORGANIZANDO A PASTA DO CLIENTE ---
pasta_dist = os.path.join('dist', 'Importador_Sistec')

# Copia o arquivo config.ini (se você tiver um) para a pasta do cliente
if os.path.exists('config.ini'):
    shutil.copy('config.ini', pasta_dist)
    print("\n✅ config.ini copiado para a pasta do executável.")

print("-" * 50)
print("🚀 COMPILAÇÃO E PREPARAÇÃO CONCLUÍDAS COM SUCESSO!")
print(f"👉 Tudo o que o seu cliente precisa está na pasta: {os.path.abspath(pasta_dist)}")
print("Basta zipar essa pasta e enviar. NENHUM código-fonte (.py) vai junto!")