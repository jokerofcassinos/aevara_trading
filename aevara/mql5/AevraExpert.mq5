//+------------------------------------------------------------------+
//|                                              AevraExpert.mq5     |
//|                                  Copyright 2026, AEVRA Organism  |
//|                                             https://aevra.ai     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AEVRA Organism"
#property link      "https://aevra.ai"
#property version   "1.12"
#property strict

#include <Trade\Trade.mqh>

// --- INPUTS ---
input string   InpSocketHost = "127.0.0.1";
input int      InpSocketPort = 5555;
input string   InpSecret     = "AEVRA_SECRET_SIGMA7"; // ASCII-only secret

// --- GLOBALS ---
int            g_socket = INVALID_HANDLE;
CTrade         g_trade;
long           g_last_processed_nonce = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit() {
   g_socket = SocketCreate();
   if(g_socket == INVALID_HANDLE) return INIT_FAILED;
   
   if(!SocketConnect(g_socket, InpSocketHost, InpSocketPort, 1000)) {
      Print("AEVRA: Initial Connection Failed. Retrying in loop...");
   }
   
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   if(g_socket != INVALID_HANDLE) SocketClose(g_socket);
   EventKillTimer();
}

//+------------------------------------------------------------------+
//| Expert timer function                                            |
//+------------------------------------------------------------------+
void OnTimer() {
   if(g_socket == INVALID_HANDLE || !SocketIsConnected(g_socket)) {
      SocketConnect(g_socket, InpSocketHost, InpSocketPort, 1000);
      return;
   }
   
   uint len = SocketIsReadable(g_socket);
   if(len > 0) {
      uchar data[];
      int res = SocketRead(g_socket, data, len, 500);
      if(res > 0) {
         string msg = CharArrayToString(data);
         ProcessPacket(msg);
      }
   }
}

//+------------------------------------------------------------------+
//| Process incoming JSON packet                                     |
//+------------------------------------------------------------------+
void ProcessPacket(string json_packet) {
   // Simple JSON Routing (v1.12)
   if(StringFind(json_packet, "\"type\":\"ORDER\"") != -1) {
      ProcessOrder(json_packet);
   } else if(StringFind(json_packet, "\"type\":\"QUERY_POSITIONS\"") != -1) {
      ProcessQueryPositions(json_packet);
   }
}

void ProcessOrder(string json_packet) {
   // Extração básica de campos para redundância
   string symbol = GetJsonValue(json_packet, "symbol");
   string side = GetJsonValue(json_packet, "order_type");
   double volume = StringToDouble(GetJsonValue(json_packet, "volume"));
   string nonce_str = GetJsonValue(json_packet, "nonce");
   long nonce = StringToInteger(StringSubstr(nonce_str, 3)); // Remove "TX-"

   // Anti-Spam Check (Nonce)
   if(nonce <= g_last_processed_nonce) {
      Print("AEVRA SAFETY: Duplicate or old Nonce ignored: ", nonce_str);
      return;
   }
   
   g_last_processed_nonce = nonce;
   bool res = false;
   
   if(side == "BUY") res = g_trade.Buy(volume, symbol);
   else if(side == "SELL") res = g_trade.Sell(volume, symbol);
   
   if(res) {
      SendFeedback("{\"status\": \"FILLED\", \"nonce\": \"" + nonce_str + "\"}");
      Print("AEVRA: Order Filled -> ", symbol, " Volume: ", volume);
   } else {
      SendFeedback("{\"status\": \"FAILED\", \"nonce\": \"" + nonce_str + "\", \"error\": \"" + (string)GetLastError() + "\"}");
   }
}

void ProcessQueryPositions(string json_packet) {
   string nonce = GetJsonValue(json_packet, "nonce");
   string pos_json = "{\"type\": \"POSITIONS_RESPONSE\", \"nonce\": \"" + nonce + "\", \"positions\": [";
   
   int count = PositionsTotal();
   for(int i = 0; i < count; i++) {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket)) {
         if(i > 0) pos_json += ",";
         pos_json += "{";
         pos_json += "\"symbol\": \"" + PositionGetString(POSITION_SYMBOL) + "\",";
         pos_json += "\"volume\": " + (string)PositionGetDouble(POSITION_VOLUME) + ",";
         pos_json += "\"price\": " + (string)PositionGetDouble(POSITION_PRICE_OPEN) + ",";
         pos_json += "\"sl\": " + (string)PositionGetDouble(POSITION_SL) + ",";
         pos_json += "\"tp\": " + (string)PositionGetDouble(POSITION_TP) + ",";
         pos_json += "\"ticket\": " + (string)ticket + ",";
         pos_json += "\"pnl\": " + (string)PositionGetDouble(POSITION_PROFIT);
         pos_json += "}";
      }
   }
   pos_json += "]}";
   SendFeedback(pos_json);
}

void SendFeedback(string msg) {
   string packet = msg + "\n";
   uchar data[];
   StringToCharArray(packet, data);
   SocketSend(g_socket, data, ArraySize(data));
}

string GetJsonValue(string json, string key) {
   int key_pos = StringFind(json, "\"" + key + "\"");
   if(key_pos == -1) return "";
   int val_start = StringFind(json, ":", key_pos) + 1;
   while(StringSubstr(json, val_start, 1) == " " || StringSubstr(json, val_start, 1) == "\"") val_start++;
   int val_end = val_start;
   while(StringSubstr(json, val_end, 1) != "\"" && StringSubstr(json, val_end, 1) != "," && StringSubstr(json, val_end, 1) != "}") val_end++;
   return StringSubstr(json, val_start, val_end - val_start);
}
