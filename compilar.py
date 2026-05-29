import PyInstaller.__main__
import shutil
import os

PyInstaller.__main__.run([
    'main.py',
    '--name=Importador_Sistec',
    '--onefile',
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


arquivo_dist = os.path.join('dist', 'Importador_Sistec.exe')

# Copia o arquivo config.ini (se você tiver um) para a pasta do cliente
if os.path.exists('config.ini') and os.path.exists('dist'):
    shutil.copy('config.ini', 'dist')
    print("\n✅ config.ini copiado para a pasta dist.")

print("-" * 50)
print("🚀 COMPILAÇÃO E PREPARAÇÃO CONCLUÍDAS COM SUCESSO!")
print(f"👉 O seu executável único está pronto aqui: {os.path.abspath(arquivo_dist)}")
print("Basta enviar apenas esse arquivo .exe para o seu cliente!")