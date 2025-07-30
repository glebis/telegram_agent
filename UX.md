# ASCII Interface Cookbook for Telegram Bot MVP

This document captures various UI layouts and flows using ASCII wireframes, based on a shadcn + Next.js frontend.

---

## A. Default Chat – Text Messages

┌─Navbar───────────────────────────────────────────────────────────────┐
│ Chats ▼  🔍Search …                      🌐 EN | DE | RU   🔔3  │
└──────────────────────────────────────────────────────────────────────┘
┌──Chats────────────┬──Conversation────────────────────────┬─Sheet────┐
│  ▸ @ProjectGroup  │  09:14  Du:   Hi Bot!                │ Modell   │
│    Me             │  09:14  Bot:  Servus 🤖              │ gpt-4o   │
│  ▸ Family         │                                       │ Temp 0.7 │
│  + New Chat       │  09:15  Du:   /mode default          │ Modus ▼  │
│                   │                                       │ Auto ✓   │
│                   │      ␣  message… [Send]               │          │
└────────────────────┴──────────────────────────────────────┴──────────┘

---

## B. Image Upload in Default Mode

… messages …
␣  Nice view!
[📷 beach.jpg] [📷 sunset.png]   🗑Clear  ⤴︎Send

---

## C. Artistic Mode with Similarity View

┌Conversation──────────────────────────────┐
09:31  Du:  /mode artistic Critic
09:32  Bot: OK – Artistic/Critic aktiviert.
09:33  Du:  [📷 art_night.jpg]
09:33  Bot:
» Deep blues contrast warm neon; echoes of Edward Hopper.
Vorschlag: crop 10 % rechts für bessere Balance.

Ähnliche Bilder ▸ (5)

└───────────────────────────────────────────┘

---

## D. Pattern Selector Drawer

┌Drawer “Image Patterns”────────────────────────────┐
│  Sunset (⧉ 23)        ✓ default                  │
│  Landschaft (⧉ 15)                                │
│  Meme template (⧉ 8)                              │
│  + New Pattern                                    │
└───────────────────────────────────────────────────┘

---

## E. Config Page – YAML Editor

provider: openai/gpt-4o-mini
image_patterns:
sunset:
match: “(sunset|golden hour)”
folder: “sunsets/”
send_first: true
meme:
match: “^/meme (.*)”
generator: “meme-macro”
rules:
	•	trigger: incoming
actions:
	•	reply: “{{analysis}}”
	•	tag: [“auto”]

---

## F. Mobile Chat

┌TopBar──────────┐
│ ☰  ChatTitle   │
└────────────────┘
… messages …
[ + ]  📷  »beach.jpg« 🗑        ⤴︎ Send

---

## G. Error Toast

⚠️  Vision-model quota exhausted – falling back to OCR only.

---

## H. First-launch – Telegram Login

┌──────────────────────────────────────────────────────────────┐
│                      🤖  Bot-Portal                          │
│──────────────────────────────────────────────────────────────│
│  ▪︎Card ─ Welcome                                           │
│   «Connect your Telegram account to start chatting.»        │
│                                                             │
│              [ Log in with Telegram ]                       │
│                                                             │
│   Need help?  docs | privacy                                │
└──────────────────────────────────────────────────────────────┘

---

## I. 2FA Cloud Password Prompt

┌Dialog – Second factor──────────────────────────┐
│ Telegram requires your cloud password.         │
│                                                │
│       ▪︎Input  ••••••••••••••                  │
│                                                │
│   [Cancel]                       [ Continue ]  │
└────────────────────────────────────────────────┘

---

## J. Empty Chat State

┌──Chats (0)─────────────┬─ Conversation────────┐
│  (blank)               │                      │
│                        │  📨  No conversations│
│                        │  yet. Start by:     │
│                        │   • Sending /start  │
│                        │   • Or clicking ➕  │
└────────────────────────┴──────────────────────┘

---

## K. Pattern Creation Wizard

┌Drawer “New Image Pattern”──────────────────────────────┐
│ ▪︎Input  Name:  ____________                           │
│ ▪︎Input  Regex / Command:  _______                     │
│ ▪︎Radio   Source:  (•) Folder   ( ) Generator          │
│                Folder path: /uploads/misc/            │
│ ▪︎Checkbox  Send first match automatically ☐           │
│                                                   ─   │
│ [ Cancel ]                              [  Save ]     │
└────────────────────────────────────────────────────────┘

---

## L. Search in Chat

  Search ⚲ sunset [⟵] [⟶]  4/12
09:32  …Here is the sunset at Baltic Sea…
^ highlighted occurrences scroll into view

---

## M. YAML Validation Error

┌Card – Validation──────────────────────────────────────────┐
│ ⚠  Duplicate trigger key “incoming” at line 12.          │
│–––––––––––––––––––––––––––––│
│ provider: openai/…                                      │
│ rules:                                                    │
│   - trigger: incoming   ← line 10                         │
│   - trigger: incoming   ← line 12 (highlight)             │
│                                                           │
│  ▪︎Monaco editor …                                         │
└───────────────────────────────────────────────────────────┘

---

## N. Image Upload Progress

[ beach_raw.jpg ]  ▄▄▄▄▄▄▄▄▄▄▄▄▄  68 %  (compressing…)

---

## O. Ngrok Disconnect Banner

┌Toast────────────────────────────────────────┐
│ 🚫  Tunnel disconnected – webhook paused.   │
│      Reconnecting in 10 s…                │
└─────────────────────────────────────────────┘

---

## P. Auto Summary Insert

┌Card – Summary (auto)──────────────────────────────────┐
│ 📝  Last 20 messages condensed by gpt-4o-mini          │
│  – Decision to ship v0.2 on Friday                    │
│  – Pending: CLA review, logo update                   │
│     [Insert into chat]  [Discard]                     │
└────────────────────────────────────────────────────────┘

---

## Q. Similar Image Carousel (Telegram)

[ ▢1 ] [ ▢2 ] [ ▢3 ] ◄ ▶
Caption: “Ähnliche Bilder – Tippe zum Öffnen”

---

## R. Language Selector (Mobile Fly-out)

🌐 EN
DE
RU

---
