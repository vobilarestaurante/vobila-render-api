import base64
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import qrcode
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
DATA_DIR = Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR))).resolve()

PRODUTOS_PATH = DATA_DIR / "produtos.json"
DELIVERY_CONFIG_PATH = DATA_DIR / "delivery_web.json"
CLIENTES_PATH = DATA_DIR / "clientes_web.json"
PEDIDOS_PATH = DATA_DIR / "pedidos_web.json"
LOJA_PATH = DATA_DIR / "loja.json"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    ensure_data_dir()
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    ensure_data_dir()
    with path.open("w", encoding="utf-8") as arquivo:
        json.dump(payload, arquivo, indent=2, ensure_ascii=False)


def normalize_produto(codigo: str, produto: dict[str, Any]) -> dict[str, Any]:
    return {
        "codigo": str(codigo or produto.get("codigo", "")).strip(),
        "nome": str(produto.get("nome", "")).strip(),
        "preco": float(produto.get("preco", 0.0) or 0.0),
        "setor": str(produto.get("setor", "")).strip(),
        "unidade": str(produto.get("unidade", "un") or "un").strip(),
        "impressora": str(produto.get("impressora", "cozinha") or "cozinha").strip(),
        "abrir_qtd": str(produto.get("abrir_qtd", "nao") or "nao").strip(),
        "imagem": str(produto.get("imagem", "") or "").strip(),
        "bloqueado": str(produto.get("bloqueado", "nao") or "nao").strip(),
        "ativo": bool(produto.get("ativo", True)),
    }


def read_produtos() -> dict[str, dict[str, Any]]:
    dados = read_json(PRODUTOS_PATH, {})
    if isinstance(dados, list):
        dados = {
            str(item.get("codigo", "")).strip(): item
            for item in dados
            if isinstance(item, dict) and str(item.get("codigo", "")).strip()
        }
    if not isinstance(dados, dict):
        return {}
    return {
        codigo: normalize_produto(codigo, produto)
        for codigo, produto in dados.items()
        if isinstance(produto, dict)
    }


def default_delivery_config() -> dict[str, Any]:
    return {
        "produtos": {},
        "layout": {
            "banners_index": [],
            "banner_intervalo_ms": 5000,
            "cor_topo": "",
            "cor_texto_topo": "",
            "nome_logo": "",
            "logo_topo": "",
            "cor_hover_produto": "",
            "cor_texto_hover_produto": "",
            "cor_botao_hover_produto": "",
            "cor_texto_botao_hover_produto": "",
            "cor_rodape": "",
            "cor_texto_rodape": "",
            "logo_rodape": "",
        },
        "operacao": {
            "fechado": False,
            "fechado_ate": "",
            "mensagem_fechado": "Delivery temporariamente fechado. Tente novamente mais tarde.",
        },
    }


def read_delivery_config() -> dict[str, Any]:
    padrao = default_delivery_config()
    dados = read_json(DELIVERY_CONFIG_PATH, {})
    if not isinstance(dados, dict):
        return padrao
    if isinstance(dados.get("layout"), dict):
        padrao["layout"].update(dados["layout"])
    if isinstance(dados.get("operacao"), dict):
        padrao["operacao"].update(dados["operacao"])
    produtos = dados.get("produtos", {})
    if isinstance(produtos, dict):
        padrao["produtos"] = {
            codigo: normalize_produto(codigo, produto)
            for codigo, produto in produtos.items()
            if isinstance(produto, dict)
        }
    return padrao


def read_clientes() -> list[dict[str, Any]]:
    dados = read_json(CLIENTES_PATH, [])
    return dados if isinstance(dados, list) else []


def write_clientes(clientes: list[dict[str, Any]]) -> None:
    write_json(CLIENTES_PATH, clientes)


def read_pedidos() -> list[dict[str, Any]]:
    dados = read_json(PEDIDOS_PATH, [])
    return dados if isinstance(dados, list) else []


def write_pedidos(pedidos: list[dict[str, Any]]) -> None:
    write_json(PEDIDOS_PATH, pedidos)


def read_loja() -> dict[str, Any]:
    dados = read_json(LOJA_PATH, {})
    return dados if isinstance(dados, dict) else {}


def delivery_status() -> dict[str, Any]:
    operacao = read_delivery_config().get("operacao", {})
    fechado = bool(operacao.get("fechado", False))
    fechado_ate = str(operacao.get("fechado_ate", "") or "").strip()
    if fechado and fechado_ate:
        try:
            limite = datetime.fromisoformat(fechado_ate)
            if datetime.now() >= limite:
                fechado = False
        except ValueError:
            pass
    return {
        "fechado": fechado,
        "fechado_ate": fechado_ate,
        "mensagem_fechado": str(
            operacao.get("mensagem_fechado")
            or "Delivery temporariamente fechado. Tente novamente mais tarde."
        ),
    }


def produtos_ativos() -> dict[str, dict[str, Any]]:
    config = read_delivery_config()
    produtos = config.get("produtos", {})
    if not produtos:
        produtos = read_produtos()
    ativos = {}
    for codigo, produto in produtos.items():
        produto = normalize_produto(codigo, produto)
        if not produto["codigo"] or not produto["nome"]:
            continue
        if not produto.get("ativo", True):
            continue
        if produto.get("bloqueado", "nao").strip().lower() == "sim":
            continue
        ativos[produto["codigo"]] = produto
    return ativos


def next_order_number(pedidos: list[dict[str, Any]]) -> int:
    maior = 0
    for pedido in pedidos:
        try:
            maior = max(maior, int(pedido.get("numero", 0) or 0))
        except (TypeError, ValueError):
            continue
    return maior + 1


def build_static_pix(valor: float) -> dict[str, Any]:
    loja = read_loja()
    pix_cfg = loja.get("pix", {}) if isinstance(loja.get("pix"), dict) else {}
    chave = str(pix_cfg.get("chave", "")).strip()
    if not chave:
        raise HTTPException(status_code=400, detail="Chave PIX nao configurada.")

    payload = f"PIX|{chave}|{valor:.2f}"
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "modo": "estatico",
        "payload": payload,
        "qr_base64": qr_base64,
        "valor": valor,
        "payment_id": None,
        "verificacao_automatica": False,
        "chave": chave,
        "mensagem": "",
    }


class ClientePayload(BaseModel):
    nome: str
    telefone: str
    endereco: str = ""
    cpf: str = ""
    email: str = ""


class PixPayload(BaseModel):
    valor: float
    modo: str | None = None
    payment_id: str | None = None


class PedidoItemPayload(BaseModel):
    codigo: str
    nome: str | None = None
    quantidade: float = 1.0
    valor_unitario: float | None = None
    preco_unitario: float | None = None
    impressora: str | None = None
    setor: str | None = None
    unidade: str | None = None
    observacao: str = ""


class PedidoPayload(BaseModel):
    nome: str
    endereco: str
    telefone: str
    referencia: str = ""
    forma_pagamento: str = "Dinheiro"
    troco: str = ""
    latitude: str | None = None
    longitude: str | None = None
    pagamento_online: dict[str, Any] = Field(default_factory=dict)
    itens: list[PedidoItemPayload]


app = FastAPI(title="Vobila Delivery API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/produtos")
def get_produtos() -> dict[str, Any]:
    return {"ok": True, "produtos": list(produtos_ativos().values())}


@app.get("/delivery-web-config")
def get_delivery_config() -> dict[str, Any]:
    config = read_delivery_config()
    return {
        "ok": True,
        "config": {
            "layout": config.get("layout", {}),
            "operacao": delivery_status(),
        },
    }


@app.get("/clientes")
def get_clientes() -> dict[str, Any]:
    return {"ok": True, "clientes": read_clientes()}


@app.get("/pedidos-status")
def get_pedidos_status(numero: list[str] | None = None) -> dict[str, Any]:
    numeros = {str(item).strip() for item in (numero or []) if str(item).strip()}
    pedidos = []
    for pedido in read_pedidos():
        numero_pedido = str(pedido.get("numero", "")).strip()
        if numeros and numero_pedido not in numeros:
            continue
        pedidos.append(
            {
                "numero": numero_pedido,
                "status": str(pedido.get("status", "Em aberto")),
                "despachado": bool(pedido.get("despachado", False)),
                "data_despacho": str(pedido.get("data_despacho", "")),
            }
        )
    return {"ok": True, "pedidos": pedidos}


@app.post("/cliente")
def save_cliente(payload: ClientePayload) -> dict[str, Any]:
    nome = payload.nome.strip()
    telefone = payload.telefone.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome do cliente nao informado.")
    if len("".join(ch for ch in telefone if ch.isdigit())) < 10:
        raise HTTPException(status_code=400, detail="Telefone do cliente invalido.")

    clientes = read_clientes()
    cliente_salvo = {
        "nome": nome.upper(),
        "telefone": telefone,
        "endereco": payload.endereco.strip(),
        "cpf": payload.cpf.strip(),
        "email": payload.email.strip(),
        "pontos": 0,
    }

    indice_existente = None
    telefone_digits = "".join(ch for ch in telefone if ch.isdigit())
    for indice, cliente in enumerate(clientes):
        cliente_telefone = "".join(ch for ch in str(cliente.get("telefone", "")) if ch.isdigit())
        if telefone_digits and cliente_telefone == telefone_digits:
            indice_existente = indice
            break

    if indice_existente is None:
        clientes.append(cliente_salvo)
    else:
        pontos = int(clientes[indice_existente].get("pontos", 0) or 0)
        cliente_salvo["pontos"] = pontos
        clientes[indice_existente] = cliente_salvo
    write_clientes(clientes)
    return {"ok": True, "cliente": cliente_salvo}


@app.post("/pedido")
def create_pedido(payload: PedidoPayload) -> dict[str, Any]:
    status = delivery_status()
    if status.get("fechado"):
        raise HTTPException(status_code=400, detail=status.get("mensagem_fechado") or "Delivery fechado.")

    if not payload.itens:
        raise HTTPException(status_code=400, detail="Pedido sem itens.")

    produtos = produtos_ativos()
    pedidos = read_pedidos()
    numero = next_order_number(pedidos)
    total = 0.0
    itens = []
    for item in payload.itens:
        produto_base = produtos.get(item.codigo)
        if not produto_base:
            raise HTTPException(status_code=400, detail=f"Produto {item.codigo} nao encontrado.")
        valor_unitario = item.valor_unitario
        if valor_unitario is None:
            valor_unitario = item.preco_unitario
        if valor_unitario is None:
            valor_unitario = float(produto_base.get("preco", 0.0) or 0.0)
        quantidade = float(item.quantidade or 1.0)
        total_item = round(float(valor_unitario) * quantidade, 2)
        total += total_item
        itens.append(
            {
                "codigo": item.codigo,
                "nome": item.nome or produto_base.get("nome", "Produto"),
                "quantidade": quantidade,
                "valor_unitario": float(valor_unitario),
                "preco": total_item,
                "impressora": item.impressora or produto_base.get("impressora", "cozinha"),
                "setor": item.setor or produto_base.get("setor", ""),
                "unidade": item.unidade or produto_base.get("unidade", "un"),
                "observacao": item.observacao.strip(),
            }
        )

    pedido = {
        "identificador": f"{payload.nome.strip().upper()}-{numero}",
        "numero": numero,
        "nome": payload.nome.strip(),
        "endereco": payload.endereco.strip(),
        "telefone": payload.telefone.strip(),
        "referencia": payload.referencia.strip(),
        "forma_pagamento": payload.forma_pagamento.strip() or "Dinheiro",
        "troco": payload.troco.strip(),
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "pagamento_online": payload.pagamento_online,
        "itens": itens,
        "total": round(total, 2),
        "status": "Em aberto",
        "despachado": False,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    pedidos.append(pedido)
    write_pedidos(pedidos)
    return {
        "ok": True,
        "pedido": {
            "identificador": pedido["identificador"],
            "numero": pedido["numero"],
            "total": pedido["total"],
        },
    }


@app.post("/pix")
def create_pix(payload: PixPayload) -> dict[str, Any]:
    if payload.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do PIX invalido.")
    return {"ok": True, "pix": build_static_pix(payload.valor)}


@app.post("/pix-status")
def pix_status(payload: PixPayload) -> dict[str, Any]:
    return {
        "ok": True,
        "pix": {
            "aprovado": False,
            "verificacao_automatica": False,
            "mensagem": "Verificacao automatica ainda nao configurada neste backend Render.",
        },
    }

