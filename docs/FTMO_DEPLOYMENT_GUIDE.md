# 🏛️ AEVRA — GUIA DE DEPLOYMENT: DESAFIO FTMO
## Protocolo: CCD-v2.0 + Zero-Trust + FTMO-Compliant (Ω-11)

Este guia detalha o processo de ativação operacional do **Aevra** para a Fase 1 do desafio de capital proprietário (FTMO ou similar).

---

## 🏗️ 1. ESTRUTURA DO DEPLOYMENT
O organismo opera em modo de **Gestão de Portfólio (v1.0.0-rc4)**, traduzindo sinais bayesianos Thompson Sampling em ordens atômicas no MT5, filtradas pelo `FTMOManager`.

- **Juiz Implacável**: `aevara/src/deployment/ftmo_manager.py` (Enforce 4%/8% Hard-Halt)
- **Elo Físico**: `aevara/src/deployment/live_connector.py` (Reconciliação 3s)
- **Modo Seguro**: `aevara/src/deployment/pilot_controller.py` (Lock 0.01 lotes)

---

## 📦 2. CONFIGURAÇÃO DA CONTA FTMO
1. **Servidor**: Utilize o servidor específico fornecido pela FTMO (ex: `FTMO-Demo` ou `FTMO-Real`).
2. **Alavancagem**: Recomenda-se 1:100 (Swing) ou 1:30 (standard). O bot ajusta o CVAr dinamicamente.
3. **Credenciais**: `mt5_adapter.py` utiliza credenciais via `CredentialVault`. Nunca utilize no código fonte.

---

## 🚀 3. PROCEDIMENTO DE ATIVAÇÃO

### Passo 1: Iniciar Servidores & Bridge
No PowerShell, execute o launcher para o desafio:
```powershell
.\aevara\scripts\start_ftmo_challenge.ps1 -AccountID "FTMO-123456" -Balance 100000.0
```

### Passo 2: Validar o Painel FTMO
O dashboard emitirá o status situacional a cada 10s:
- **Profit Target**: 8% ($8,000)
- **Daily DD Limit**: 4% ($4,000 buffer interno / FTMO é 5%)
- **Total DD Limit**: 8% ($8,000 buffer interno / FTMO é 10%)

### Passo 3: Período Pilot (Aqueceimento)
Durante os primeiros **10 trades** (ou 24h), o bot operará em **0.01 lotes** independentemente do sinal. O `PilotController` só desbloqueará a alocação completa se o `stability_score` for > 0.95 (zero drifts significativos no terminal).

---

## 🛡️ 4. PROTOCOLOS DE EMERGÊNCIA
- **Emergency Halt (DD > 4%)**: O bot interrompe toda nova entrada e emite alerta `FTMO ALERT`.
- **Position Flattening**: Em caso de violação de 8% de perda total, o sistema tentará fechar todas as posições via Socket Bridge e travar o bot.
- **Drift Correction (3s)**: Se você fechar uma ordem manualmente no MT5, o `LiveConnector` detectará a discrepância em 3s e reconciliará o estado interno.

---

> 📌 **Nota Executiva**: O Desafio FTMO é um teste de **Sobrevivência**, não apenas de performance. O Aevra prioriza o `Survival Probability` de 99.5% sobre o lucro imediato.

**AEVRA SOBERANO — DESAFIO ATIVO.** 🃏🛡️🚀🔗
