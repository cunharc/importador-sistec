import locale
if not hasattr(locale, 'resetlocale'):
    locale.resetlocale = lambda: locale.setlocale(locale.LC_ALL, "")

import fdb
import time
import argparse
from typing import List, Dict, Any, Callable, Optional

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
        self.fbclient = config.get('fbclient')
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
    
    print(f"Tentando conectar em {args.host}:{args.port} -> {args.database}")
    try:
        with FirebirdService(config) as fb:
            print("Conexão estabelecida com sucesso!")
            # Exemplo de consulta simples para testar
            res = fb.query("SELECT 1 AS TESTE FROM RDB$DATABASE")
            print(f"Resultado do teste: {res}")
    except Exception as e:
        print(f"Erro: {e}")