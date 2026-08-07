import PyInstaller.__main__
import shutil
import os
import sys

# O console do Windows abre em cp1252 e os avisos daqui têm ✅. Sem isto o script
# morria de UnicodeEncodeError NO PRINT FINAL, depois de o .exe já estar pronto —
# e o publicar.py, que confere o código de saída, dava "a compilação falhou".
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

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
    # main.py:53 e telas/tela_inicial.py:80 abrem este PNG por resource_path() —
    # sem embutir, o logo da tela inicial nao aparece no .exe (estava no build.spec
    # mas nunca aqui, e este e o script que compila de verdade)
    '--add-data=Logo oficial grupos - Sistec.png;.',
    '--add-data=ncm_governo.json;.',
    '--add-data=cfop_governo.json;.',
    '--add-data=config_modulos_log.json;.',
    '--add-binary=fbclient_*.dll;.',
    # Otimizações: Exclui módulos pesados que não são usados no seu sistema
    '--exclude-module=matplotlib',
    '--exclude-module=numpy',
    '--exclude-module=scipy',
    '--exclude-module=pandas',
    '--exclude-module=PyQt5',
    '--exclude-module=tkinter.test',
    '--exclude-module=unittest'
])


arquivo_dist = os.path.join('dist', 'Importador_Sistec.exe')

# Copia o config.ini para a pasta do cliente. Se nao existir (clone novo), leva o
# modelo com o nome final — o .exe nao vem com config embutido e sem o arquivo a
# primeira abertura ficaria sem banco configurado.
if os.path.exists('dist'):
    if os.path.exists('config.ini'):
        shutil.copy('config.ini', 'dist')
        print("\n✅ config.ini copiado para a pasta dist.")
    elif os.path.exists('config.ini.exemplo'):
        shutil.copy('config.ini.exemplo', os.path.join('dist', 'config.ini'))
        print("\n⚠ Nao havia config.ini: o modelo foi para dist/config.ini. "
              "Configure o banco na primeira abertura.")

print("-" * 50)
print("🚀 COMPILAÇÃO E PREPARAÇÃO CONCLUÍDAS COM SUCESSO!")
print(f"👉 O seu executável único está pronto aqui: {os.path.abspath(arquivo_dist)}")
print("Basta enviar apenas esse arquivo .exe para o seu cliente!")