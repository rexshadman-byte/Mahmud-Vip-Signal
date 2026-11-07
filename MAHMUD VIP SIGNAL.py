import json
import time
import requests

API_TOKEN = "9052596382:AAHV-NtfN_-rkQNke8c203C86MaSUmNn5Jc"
LOTTERY_API = (
    "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
)
TELEGRAM_URL = f"https://api.telegram.org/bot{API_TOKEN}"

active_users = (
    set()
)  # যারা সিগন্যাল রিসিভ করার জন্য 'Get Signal' অন করে রেখেছে
all_users = set()  # সকল ইউজার যারা বট স্টার্ট করেছে
last_processed_period = ""
active_signals = {}  # {period: {chat_id: message_id}}
session_history = []  # শেষ ১০টি সিগন্যালের হিস্ট্রি
user_last_message = {}  # মেনু বা সিগন্যাল মেসেজ আইডি ট্র্যাক করার জন্য


def get_lottery_data():
  try:
    res = requests.get(LOTTERY_API, timeout=5)
    if res.status_code == 200:
      return res.json().get("data", {}).get("list", [])
  except Exception as e:
    print("API Error:", e)
  return []


def calculate_prediction(target_issue, history):
  recent_nums = [int(item.get("number", 0)) for item in history[:25]]
  recent_types = ["BIG" if n >= 5 else "SMALL" for n in recent_nums]

  aggressive_score = 0
  for idx, t in enumerate(recent_types[:10]):
    weight = 10 - idx
    if t == "BIG":
      aggressive_score += weight
    else:
      aggressive_score -= weight

  pred_type = "BIG" if aggressive_score >= 0 else "SMALL"

  if (
      len(recent_types) >= 3
      and recent_types[0] == recent_types[1]
      and recent_types[1] == recent_types[2]
  ):
    pred_type = "SMALL" if recent_types[0] == "BIG" else "BIG"

  candidate_numbers = [5, 6, 7, 8, 9] if pred_type == "BIG" else [0, 1, 2, 3, 4]
  issue_tail = int(target_issue[-3:]) if target_issue.isdigit() else 0

  ultra_hash = (
      issue_tail * 7
      + recent_nums[0] * 11
      + recent_nums[1] * 3
      + recent_nums[2] * 5
  ) % len(candidate_numbers)
  predicted_number = candidate_numbers[ultra_hash]

  return target_issue, predicted_number, pred_type


def send_main_menu(chat_id):
  text = (
      "👑 **𝐌𝐓 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐎𝐓 𝐒𝐈𝐆𝐍𝐀𝐋** 👑\n"
      "━━━━━━━━━━━━━━━━━━━━━━━\n"
      "স্বাগতম! নিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় বাটনটিতে ক্লিক করুন:\n"
      "━━━━━━━━━━━━━━━━━━━━━━━"
  )
  reply_markup = {
      "inline_keyboard": [
          [{"text": "🎯 Get Signal", "callback_data": "get_signal"}],
          [{"text": "📜 Last 10 History", "callback_data": "show_history"}],
      ]
  }
  url = f"{TELEGRAM_URL}/sendMessage"
  payload = {
      "chat_id": chat_id,
      "text": text,
      "parse_mode": "Markdown",
      "reply_markup": json.dumps(reply_markup),
  }
  try:
    res = requests.post(url, json=payload).json()
    if res.get("ok"):
      user_last_message[chat_id] = res["result"]["message_id"]
  except Exception as e:
    print("Menu Send Error:", e)


def edit_message(chat_id, message_id, text, reply_markup=None):
  url = f"{TELEGRAM_URL}/editMessageText"
  payload = {
      "chat_id": chat_id,
      "message_id": message_id,
      "text": text,
      "parse_mode": "Markdown",
  }
  if reply_markup:
    payload["reply_markup"] = json.dumps(reply_markup)
  try:
    requests.post(url, json=payload)
  except Exception as e:
    print("Edit Error:", e)


def send_telegram_message(chat_id, text, reply_markup=None):
  url = f"{TELEGRAM_URL}/sendMessage"
  payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
  if reply_markup:
    payload["reply_markup"] = json.dumps(reply_markup)
  try:
    res = requests.post(url, json=payload).json()
    if res.get("ok"):
      return res["result"]["message_id"]
  except Exception as e:
    print("Send Error:", e)
  return None


def delete_telegram_message(chat_id, message_id):
  url = f"{TELEGRAM_URL}/deleteMessage"
  payload = {"chat_id": chat_id, "message_id": message_id}
  try:
    requests.post(url, json=payload)
  except Exception as e:
    print("Delete Error:", e)


def main():
  global last_processed_period, session_history
  offset = 0
  print("🤖 MT PREMIUM BUTTON BOT is running...")

  while True:
    # ১. টেলিগ্রাম আপডেট ও বাটন ক্লিক হ্যান্ডেল করা
    try:
      updates_url = f"{TELEGRAM_URL}/getUpdates?offset={offset}&timeout=2"
      res = requests.get(updates_url, timeout=5).json()
      for result in res.get("result", []):
        offset = result["update_id"] + 1

        # যদি ইউজার মেসেজ দেয় (/start)
        if "message" in result:
          message = result["message"]
          chat_id = message.get("chat", {}).get("id")
          text = message.get("text", "")
          if chat_id and text.startswith("/start"):
            all_users.add(chat_id)
            if chat_id in active_users:
              active_users.remove(
                  chat_id
              )  # নতুন স্টার্ট দিলে সিগন্যাল অফ করে মেনুতে আনবে
            send_main_menu(chat_id)

        # যদি ইউজার ইনলাইন বাটনে ক্লিক করে
        elif "callback_query" in result:
          query = result["callback_query"]
          chat_id = query["message"]["chat"]["id"]
          message_id = query["message"]["message_id"]
          data = query["data"]

          # ১. Get Signal বাটনে ক্লিক করলে
          if data == "get_signal":
            active_users.add(chat_id)
            back_markup = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Menu", "callback_data": "back_menu"}]
                ]
            }
            edit_message(
                chat_id,
                message_id,
                "👑 **𝐌𝐓 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐎𝐓 𝐒𝐈𝐆𝐍𝐀𝐋** 👑\n━━━━━━━━━━━━━━━━━━━━━━━\n🟢"
                " **Signal Streaming Activated!**\nWaiting for the next round"
                " prediction...\n━━━━━━━━━━━━━━━━━━━━━━━",
                back_markup,
            )

          # ২. Last 10 History বাটনে ক্লিক করলে
          elif data == "show_history":
            total_signals = len(session_history)
            total_wins = sum(1 for x in session_history if x["status"] == "WIN")
            total_losses = sum(
                1 for x in session_history if x["status"] == "LOSS"
            )

            history_text = (
                "👑 **𝐌𝐓 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐎𝐓 - 𝐋𝐀𝐒𝐓 𝟏𝟎 𝐒𝐈𝐆𝐍𝐀𝐋𝐒** 👑\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            if not session_history:
              history_text += "*No history available yet. Play a few rounds!*\n"
            else:
              for idx, item in enumerate(session_history, 1):
                status_icon = (
                    "🟢 **WIN**" if item["status"] == "WIN" else "🔴 **LOSS**"
                )
                history_text += (
                    f"`{idx}.` P:`{item['period']}` | 🎯 **{item['type']}** | 🔢"
                    f" `{item['pred_num']}` → {status_icon}\n"
                )

            history_text += (
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Total Tracked:** `{total_signals}` | ✅"
                f" **Wins:** `{total_wins}` | ❌ **Losses:** `{total_losses}`"
            )
            back_markup = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Menu", "callback_data": "back_menu"}]
                ]
            }
            edit_message(chat_id, message_id, history_text, back_markup)

          # ৩. Back to Menu বাটনে ক্লিক করলে
          elif data == "back_menu":
            if chat_id in active_users:
              active_users.remove(
                  chat_id
              )  # মেনুতে ফিরলে সিগন্যাল স্ট্রিমিং বন্ধ হবে
            # পুরোনো মেসেজ ডিলিট করে ফ্রেশ মেনু পাঠানো
            delete_telegram_message(chat_id, message_id)
            send_main_menu(chat_id)

    except Exception as e:
      print("Update/Callback Error:", e)

    # ২. লটারি এপিআই ফেচ ও সিগন্যাল প্রসেসিং
    history = get_lottery_data()
    if history:
      latest_issue = str(history[0].get("issueNumber", ""))
      actual_num = int(history[0].get("number", 0))
      actual_type = "BIG" if actual_num >= 5 else "SMALL"

      # রাউন্ড শেষ হলে উইন/লস আপডেট করা
      if latest_issue in active_signals:
        for cid, info in active_signals[latest_issue].items():
          msg_id = info["msg_id"]
          pred_type = info["pred_type"]
          res_status = "🟢 **WIN**" if pred_type == actual_type else "🔴 **LOSS**"

          updated_text = (
              "👑 **𝐌𝐓 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐎𝐓 𝐒𝐈𝐆𝐍𝐀𝐋** 👑\n"
              "━━━━━━━━━━━━━━━━━━━━━━━\n"
              f"📊 **Period:** `{latest_issue[-4:]}`\n"
              f"🎯 **Signal:** **{pred_type}**\n"
              f"🔢 **Number Shot:** `{info['pred_num']}`\n"
              f"🎲 **Result:** `{actual_num} ({actual_type})`\n"
              f"📌 **Status:** {res_status}\n"
              "━━━━━━━━━━━━━━━━━━━━━━━"
          )
          back_markup = {
              "inline_keyboard": [
                  [{"text": "🔙 Back to Menu", "callback_data": "back_menu"}]
              ]
          }
          edit_message(cid, msg_id, updated_text, back_markup)

          # হিস্ট্রিতে যুক্ত করা (সর্বোচ্চ ১০টি সংরক্ষণ করবে)
          session_history.insert(
              0,
              {
                  "period": latest_issue[-4:],
                  "type": pred_type,
                  "pred_num": info["pred_num"],
                  "status": "WIN" if pred_type == actual_type else "LOSS",
              },
          )
          if len(session_history) > 10:
            session_history.pop()

        del active_signals[latest_issue]

      # নতুন পিরিয়ডের সিগন্যাল জেনারেট করে শুধু 'Get Signal' অন করা ইউজারদের পাঠানো
      if latest_issue:
        next_issue = str(int(latest_issue) + 1)
        if last_processed_period != next_issue:
          last_processed_period = next_issue
          target_issue, pred_num, pred_type = calculate_prediction(
              next_issue, history
          )

          signal_text = (
              "👑 **𝐌𝐓 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐎𝐓 𝐒𝐈𝐆𝐍𝐀𝐋** 👑\n"
              "━━━━━━━━━━━━━━━━━━━━━━━\n"
              f"📊 **Period:** `{target_issue[-4:]}`\n"
              f"🎯 **Signal:** **{pred_type}**\n"
              f"🔢 **Number Shot:** `{pred_num}`\n"
              "━━━━━━━━━━━━━━━━━━━━━━━"
          )
          back_markup = {
              "inline_keyboard": [
                  [{"text": "🔙 Back to Menu", "callback_data": "back_menu"}]
              ]
          }

          active_signals[target_issue] = {}
          for cid in list(active_users):
            new_msg_id = send_telegram_message(
                cid, signal_text, back_markup
            )
            if new_msg_id:
              active_signals[target_issue][cid] = {
                  "msg_id": new_msg_id,
                  "pred_type": pred_type,
                  "pred_num": pred_num,
              }

    time.sleep(3)


if __name__ == "__main__":
  main()
