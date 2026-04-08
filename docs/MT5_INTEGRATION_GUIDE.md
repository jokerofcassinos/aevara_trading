# 🏛️ AEVRA — GUIA DE INTEGRAÇÃO METATRADER 5 (MT5)
## Protocolo: CCD-v2.0 + Zero-Trust + Async-First

Este guia detalha o processo de conexão do núcleo cognitivo do **Aevra** ao terminal **MetaTrader 5 (MT5)** para execução live de capital real.

---

## 🏗️ 1. ESTRUTURA DO BRIDGE
A integração opera via **TCP Sockets (Build 1880+)**, permitindo comunicação bidirecional assíncrona entre o cérebro Python e o EA MQL5.

- **Servidor (Python)**: `aevara/src/execution/mt5_adapter.py`
- **Cliente (MQL5)**: `aevara/mql5/AevraExpert.mq5`
- **Configuração**: `aevara/config/mt5_config.yaml`

---

## 📦 2. REQUISITOS PRÉVIOS
1. **MetaTrader 5 Terminal** instalado (Windows 64-bit).
2. **Conta Demo ativa** (recomendado servidor FTMO ou IC Markets).
3. **Python 3.10+** com ambiente virtual configurado.
4. **Habilitar WebRequest & Sockets** no MT5:
   - `Tools` → `Options` → `Expert Advisors` → Marcar `Allow DLL imports` & `Allow WebRequest for listed URL`.
   - Adicionar `http://127.0.0.1` e `https://aevra.ai` se necessário.

---

## 🚀 3. PROCEDIMENTO DE DEPLOYMENT

### Passo 1: Inicializar o Servidor Python
No terminal PowerShell, execute o script de deployment:
```powershell
.\aevara\scripts\deploy_mt5.ps1 -Port 5555 -SecretKey "AEVRA_SECRET_Ω7"
```
Este script iniciará o servidor TCP que aguardará a conexão do MT5.

### Passo 2: Instalar o Expert Advisor (EA)
1. Abra o **MetaEditor** (F4 no MT5).
2. Arraste `aevara/mql5/AevraExpert.mq5` para a pasta `MQL5/Experts` do seu terminal MT5.
3. Pressione **F7** para compilar. Garanta que 0 erros foram reportados.
4. No terminal MT5, arraste o **AevraExpert** para um gráfico (ex: BTCUSD, M1).

### Passo 3: Configurar Parâmetros do EA
- `InpSocketHost`: `127.0.0.1`
- `InpSocketPort`: `5555`
- `InpSecret`: `AEVRA_SECRET_Ω7` (Deve ser idêntico ao do servidor Python)
- `InpAllowTrading`: `true`

---

## 🛡️ 4. SEGURANÇA & ZERO-TRUST (HMAC)
Cada ordem enviada pelo Python contém uma assinatura **HMAC-SHA256**. O EA MQL5 valida a assinatura antes de qualquer execução (`TRADE_ACTION_DEAL`). Isso impede que hackers ou softwares de terceiros injetem ordens falsas no socket aberto localmente.

---

## 🔄 5. RECONCILIAÇÃO & IDEMPOTÊNCIA
- **Nonce-based**: Cada pedido de ordem possui um ID único (`TX-TIMESTAMP`).
- **Confirmation Loop**: O Python aguarda o feedback do `OrderSend` antes de atualizar o estado interno (`FILLED`, `REJECTED`, `EXPIRED`).
- **Drift Check**: A cada 5 segundos, o `FailoverManager` consulta as posições abertas no MT5 e corrige qualquer discrepância.

---

## ⚠️ 6. TROUBLESHOOTING
- **"SocketConnect failed (4006)"**: O servidor Python não está rodando ou a porta 5555 está bloqueada pelo Firewall.
- **"Invalid HMAC Signature"**: O segredo no arquivo YAML não coincide com o `InpSecret` do EA no MT5.
- **"OrderSend failed (4756)"**: Verifique se o `AlgoTrading` está habilitado na barra superior do MT5 (ícone verde).

---

> 📌 **Nota Executiva**: Nunca compartilhe o `SecretKey` fora do ambiente de deployment seguro. O vazamento do segredo permite a execução de ordens não autorizadas no terminal.

**AEVRA SOBERANO — PROTOCOLO DE EXECUÇÃO ATIVO.** 🃏⚡🔗
