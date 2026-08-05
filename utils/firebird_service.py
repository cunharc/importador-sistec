import locale
if not hasattr(locale, 'resetlocale'):
    locale.resetlocale = lambda: locale.setlocale(locale.LC_ALL, "")

import fdb
import os
import sys
import time
import argparse
from typing import List, Dict, Any, Callable, Optional


def resolver_fbclient(nome):
    """Transforma 'fbclient_5.dll' num caminho absoluto.

    A partir do Python 3.8 o `ctypes` não procura mais DLL no diretório atual, então
    um nome relativo só conecta por acidente — quando alguma outra conexão do mesmo
    processo já carregou a biblioteca. Foi assim que as telas de Receber e Pagar
    ficaram sem centro de custo: `carregar_opcoes` não conseguia conectar e devolvia
    listas vazias. Procura ao lado do executável empacotado, na raiz do projeto e no
    diretório atual, nessa ordem; não achando, devolve o que veio (o fdb tenta pelo
    PATH e a mensagem de erro fica clara).
    """
    if not nome:
        return nome
    if os.path.isabs(nome):
        return nome
    bases = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        bases.append(meipass)
    if getattr(sys, 'frozen', False):
        bases.append(os.path.dirname(sys.executable))
    bases.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bases.append(os.getcwd())
    for base in bases:
        caminho = os.path.join(base, nome)
        if os.path.isfile(caminho):
            return caminho
    return nome


class FirebirdService:
    """
    Serviço de conexão e operações com o banco de dados Firebird.
    Implementa retentativas de conexão e gerenciamento de transações.
    """
    def __init__(self, config: Dict[str, Any]):
        self.host = config.get('host', '127.0.0.1')
        self.port = int(config.get('port', 3050))
        self.database = config.get('database')
        self.user = config.get('user', 'SYSDBA')
        self.password = config.get('password', 'masterkey')
        self.charset = config.get('charset', 'WIN1252')
        self.fbclient = resolver_fbclient(config.get('fbclient'))
        self.conn: Optional[fdb.Connection] = None

    def connect(self, retries: int = 3, delay_ms: int = 500) -> None:
        """
        Estabelece a conexão com o banco de dados com suporte a retentativas.
        """
        if not self.database:
            raise ValueError("O caminho do banco de dados (database) não foi informado na configuração.")

        dsn = f"{self.host}/{self.port}:{self.database}" if self.host else self.database
        
        kwargs = {
            'dsn': dsn,
            'user': self.user,
            'password': self.password,
            'charset': self.charset
        }
        
        if self.fbclient:
            kwargs['fb_library_name'] = self.fbclient

        last_error = None
        for attempt in range(retries):
            try:
                self.conn = fdb.connect(**kwargs)
                return
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                
                # Tratamento especial para falha de login que pode ser intermitente
                if 'user name and password' in error_msg:
                    time.sleep(delay_ms / 1000.0)
                    continue
                else:
                    time.sleep(delay_ms / 1000.0)
                    
        raise ConnectionError(f"Falha ao conectar ao Firebird após {retries} tentativas: {last_error}")

    def query(self, sql: str, params: list = None) -> List[Dict[str, Any]]:
        """
        Executa uma consulta SELECT e retorna uma lista de dicionários.
        As chaves dos dicionários estarão em letras minúsculas.
        """
        if not self.conn:
            self.connect()
            
        params = params or []
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            columns = [col[0].lower() for col in cur.description]
            results = []
            for row in cur.fetchall():
                results.append(dict(zip(columns, row)))
            return results
        finally:
            cur.close()

    def execute(self, sql: str, params: list = None) -> None:
        """
        Executa um comando INSERT, UPDATE ou DELETE sem retorno de dados.
        """
        if not self.conn:
            self.connect()
            
        params = params or []
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            cur.close()

    def transaction(self, callback: Callable[[fdb.Cursor], Any]) -> Any:
        """
        Abre uma transação, executa o callback passando o cursor, 
        faz COMMIT em caso de sucesso ou ROLLBACK em caso de exceção.
        """
        if not self.conn:
            self.connect()
            
        cur = self.conn.cursor()
        try:
            result = callback(cur)
            self.conn.commit()
            return result
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            cur.close()

    def detach(self) -> None:
        """
        Fecha a conexão com o banco de dados com segurança.
        """
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            finally:
                self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.detach()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Teste de conexão com o Firebird")
    parser.add_argument('--host', default='127.0.0.1', help="Host do banco de dados")
    parser.add_argument('--port', type=int, default=3050, help="Porta do banco de dados")
    parser.add_argument('--database', required=True, help="Caminho absoluto do banco de dados")
    parser.add_argument('--user', default='SYSDBA', help="Usuário do banco")
    parser.add_argument('--password', default='masterkey', help="Senha do banco")
    
    args = parser.parse_args()
    
    config = {
        'host': args.host,
        'port': args.port,
        'database': args.database,
        'user': args.user,
        'password': args.password
    }
    
    from utils.logger import get_logger
    _log = get_logger('firebird_test')
    _log.info(f"Tentando conectar em {args.host}:{args.port} -> {args.database}")
    try:
        with FirebirdService(config) as fb:
            _log.info("Conexão estabelecida com sucesso!")
            res = fb.query("SELECT 1 AS TESTE FROM RDB$DATABASE")
            _log.info(f"Resultado do teste: {res}")
    except Exception as e:
        _log.error(f"Erro: {e}")