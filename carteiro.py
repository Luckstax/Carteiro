import os
import base64
import mimetypes
import sqlite3
import unicodedata
from datetime import datetime
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKENS_DIR = os.path.join(BASE_DIR, "dados", "tokens")
DB_FILE = os.path.join(BASE_DIR, "dados", "contatos.db")
USUARIO_PADRAO_ID = 1


def buscar_usuario(usuario_id=USUARIO_PADRAO_ID):
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    try:
        usuario = con.execute(
            """SELECT id, apelido, nome, email, telefone, curriculo_path, assinatura,
                      objetivo, preferencias_json
               FROM usuarios WHERE id = ?""",
            (usuario_id,),
        ).fetchone()
        if usuario is None:
            raise ValueError(f"Usuário não encontrado: {usuario_id}")
        return usuario
    finally:
        con.close()


def caminho_token(usuario_id):
    os.makedirs(TOKENS_DIR, exist_ok=True)
    return os.path.join(TOKENS_DIR, f"usuario_{usuario_id}.json")


def autenticar(usuario_id=USUARIO_PADRAO_ID):
    usuario = buscar_usuario(usuario_id)
    token_file = caminho_token(usuario_id)
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Arquivo não encontrado: {CREDENTIALS_FILE}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


def inicializar_banco():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    con = sqlite3.connect(DB_FILE)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apelido TEXT,
                nome TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                telefone TEXT,
                curriculo_path TEXT,
                assinatura TEXT,
                objetivo TEXT,
                preferencias_json TEXT NOT NULL DEFAULT '{}',
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS historico_envios (
                id INTEGER PRIMARY KEY,
                contato_id INTEGER,
                destinatario TEXT NOT NULL,
                assunto TEXT,
                corpo TEXT,
                data_envio TEXT NOT NULL,
                gmail_id TEXT,
                status TEXT NOT NULL,
                erro TEXT,
                usuario_id INTEGER
            )
        """)

        usuario_cols = {
            row[1] for row in con.execute("PRAGMA table_info(usuarios)")
        }
        if "apelido" not in usuario_cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN apelido TEXT")

        colunas = {
            row[1] for row in con.execute("PRAGMA table_info(historico_envios)")
        }
        extras = {
            "contato_id": "INTEGER",
            "destinatario": "TEXT",
            "assunto": "TEXT",
            "corpo": "TEXT",
            "data_envio": "TEXT",
            "gmail_id": "TEXT",
            "status": "TEXT",
            "erro": "TEXT",
            "usuario_id": "INTEGER",
        }
        for nome, tipo in extras.items():
            if nome not in colunas:
                con.execute(
                    f"ALTER TABLE historico_envios ADD COLUMN {nome} {tipo}"
                )

        contatos_colunas = {
            row[1] for row in con.execute("PRAGMA table_info(contatos)")
        }
        if "usuario_id" not in contatos_colunas:
            con.execute("ALTER TABLE contatos ADD COLUMN usuario_id INTEGER")
        if "organizacao" not in contatos_colunas:
            con.execute("ALTER TABLE contatos ADD COLUMN organizacao TEXT")
        if "tipo_contato" not in contatos_colunas:
            con.execute("ALTER TABLE contatos ADD COLUMN tipo_contato TEXT")

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def buscar_contato(contato_id, usuario_id=USUARIO_PADRAO_ID):
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            """SELECT id, nome, email, sindicato, organizacao, tipo_contato,
                      regiao, status, usuario_id
               FROM contatos
               WHERE id = ? AND usuario_id = ?""",
            (contato_id, usuario_id),
        ).fetchone()
    finally:
        con.close()


def _normalizar_texto(texto):
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


def validar_corpo_personalizado(contato_id, organizacao, regiao, corpo, usuario_id=USUARIO_PADRAO_ID):
    if not corpo or not corpo.strip():
        raise ValueError("O corpo do e-mail não pode estar vazio.")

    texto = _normalizar_texto(corpo)
    nome_organizacao = _normalizar_texto(organizacao)

    if nome_organizacao and nome_organizacao not in texto:
        raise ValueError(
            "O e-mail precisa ser personalizado para a organização "
            f"'{organizacao}'. Inclua o nome ou identificação da organização no corpo."
        )

    if regiao == "Baixada":
        if "praia grande" not in texto or not any(
            termo in texto
            for termo in (
                "pretendo me mudar",
                "pretendo mudar",
                "vou me mudar",
                "mudanca para praia grande",
                "mudanca para a praia grande",
                "mudarei para praia grande",
            )
        ):
            raise ValueError(
                "Candidatura da Baixada precisa mencionar que pretende se mudar "
                "para Praia Grande."
            )

    if regiao == "SP":
        if not any(
            termo in texto
            for termo in (
                "home office",
                "trabalho remoto",
                "remota",
                "remoto",
                "teletrabalho",
            )
        ):
            raise ValueError(
                "Candidatura de SP precisa mencionar o foco em trabalho remoto/home office."
            )

    con = sqlite3.connect(DB_FILE)
    try:
        duplicado = con.execute(
            """SELECT 1 FROM historico_envios
               WHERE usuario_id = ?
                 AND status = 'enviado'
                 AND corpo = ?
                 AND contato_id <> ?
               LIMIT 1""",
            (usuario_id, corpo, contato_id),
        ).fetchone()
    finally:
        con.close()

    if duplicado:
        raise ValueError(
            "Este corpo de e-mail já foi usado em outra candidatura. "
            "Cada sindicato deve receber uma mensagem personalizada."
        )


def registrar_envio(
    contato_id,
    destinatario,
    assunto,
    corpo,
    gmail_id,
    usuario_id=USUARIO_PADRAO_ID,
):
    data_envio = datetime.now().astimezone().isoformat(timespec="seconds")
    con = sqlite3.connect(DB_FILE)
    try:
        con.execute("BEGIN")
        con.execute(
            """INSERT INTO historico_envios
               (contato_id, destinatario, assunto, corpo, data_envio,
                gmail_id, status, usuario_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                contato_id,
                destinatario,
                assunto,
                corpo,
                data_envio,
                gmail_id,
                "enviado",
                usuario_id,
            ),
        )
        con.execute(
            """UPDATE contatos
               SET status = ?, data_envio = ?
               WHERE id = ? AND usuario_id = ?""",
            ("usados", data_envio, contato_id, usuario_id),
        )
        if con.total_changes != 2:
            raise RuntimeError("Não foi possível atualizar o contato após o envio.")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def enviar_para_contato(
    contato_id,
    assunto,
    corpo,
    anexo=None,
    usuario_id=USUARIO_PADRAO_ID,
):
    inicializar_banco()
    usuario = buscar_usuario(usuario_id)
    contato = buscar_contato(contato_id, usuario_id)

    if contato is None:
        raise ValueError(
            f"Contato não encontrado para o usuário {usuario['email']}: {contato_id}"
        )

    if contato["status"] == "usados":
        raise ValueError("Este contato já está marcado como usado.")

    if contato["status"] not in ("guardados", "recém encontrados"):
        raise ValueError(
            f"Status do contato não permite envio: {contato['status']}"
        )

    validar_corpo_personalizado(
        contato_id=contato["id"],
        organizacao=contato["organizacao"] or contato["sindicato"],
        regiao=contato["regiao"],
        corpo=corpo,
        usuario_id=usuario_id,
    )

    if anexo is None:
        anexo = usuario["curriculo_path"]

    resultado = enviar_email(
        destinatario=contato["email"],
        assunto=assunto,
        corpo=corpo,
        anexo=anexo,
        usuario_id=usuario_id,
    )

    gmail_id = resultado.get("id")
    if not gmail_id:
        raise RuntimeError("O Gmail não retornou o ID da mensagem enviada.")

    registrar_envio(
        contato_id=contato_id,
        destinatario=contato["email"],
        assunto=assunto,
        corpo=corpo,
        gmail_id=gmail_id,
        usuario_id=usuario_id,
    )
    return resultado


def criar_mensagem(destinatario, assunto, corpo, anexo=None):
    mensagem = EmailMessage()
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(corpo)

    if anexo:
        if not os.path.isfile(anexo):
            raise FileNotFoundError(f"Anexo não encontrado: {anexo}")

        nome_arquivo = os.path.basename(anexo)
        tipo_mime, _ = mimetypes.guess_type(nome_arquivo)

        if tipo_mime:
            maintype, subtype = tipo_mime.split("/", 1)
        else:
            maintype = "application"
            subtype = "octet-stream"

        with open(anexo, "rb") as arquivo:
            dados = arquivo.read()

        mensagem.add_attachment(
            dados,
            maintype=maintype,
            subtype=subtype,
            filename=nome_arquivo,
        )

    return mensagem


def enviar_email(
    destinatario,
    assunto,
    corpo,
    anexo=None,
    usuario_id=USUARIO_PADRAO_ID,
):
    creds = autenticar(usuario_id)
    service = build("gmail", "v1", credentials=creds)

    mensagem = criar_mensagem(
        destinatario=destinatario,
        assunto=assunto,
        corpo=corpo,
        anexo=anexo,
    )
    mensagem["From"] = "me"

    mensagem_bytes = mensagem.as_bytes()
    mensagem_codificada = base64.urlsafe_b64encode(
        mensagem_bytes
    ).decode()

    resultado = service.users().messages().send(
        userId="me",
        body={"raw": mensagem_codificada},
    ).execute()

    return resultado


if __name__ == "__main__":
    inicializar_banco()
    usuario = buscar_usuario()
    print("Carteiro iniciado.")
    print(f"Perfil padrão: {usuario['apelido'] or usuario['nome']} | {usuario['nome']} <{usuario['email']}>")
    print("Banco SQLite inicializado.")
    print("Nenhum e-mail será enviado automaticamente.")
