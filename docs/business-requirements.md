# Business Requirements Document — GroupMe Travel Bot

## 1. Product Vision

A conversational AI bot that lives inside a GroupMe group chat and helps friends collaboratively plan vacations. The bot participates in natural conversation, captures ideas, organizes plans, and produces a polished itinerary — eliminating the need for spreadsheets, shared docs, or separate planning apps.

## 2. User Personas

| Persona | Description |
|---|---|
| **Trip Organizer** | The person who creates the GroupMe group and adds the bot. May take the lead on moving items through planning stages. |
| **Group Member** | Any participant in the chat. Contributes ideas, votes on options, and asks the bot questions about the trip. |

All group members have equal permissions when interacting with the bot.

## 3. Core Concept — Three-Stage Trip Model

Each GroupMe group has one active trip at a time. Trip data flows through three stages:

### 3.1 Brainstorming

- The default landing zone for new ideas surfaced in conversation.
- The bot captures destinations, activities, lodging options, date ranges, budget ideas, and any other travel-related topics discussed in chat.
- The bot can use web search to enrich ideas with real-time information (prices, weather, reviews, availability).
- Items in brainstorming are informal and unstructured — think sticky notes on a board.

### 3.2 Planning

- Once the group agrees on an idea, any member can tell the bot to move it from brainstorming to planning.
- The bot curates and organizes the relevant details (e.g., collapses multiple hotel discussions into a single structured entry with dates, prices, and links).
- Planning items are more structured: they have a category (lodging, transport, activity, dining, etc.), a status, and associated details.
- The bot can answer questions about what's in the planning stage and identify gaps (e.g., "we have flights but no hotel yet").

### 3.3 Finalized (Itinerary)

- Concrete, confirmed bookings with real details: confirmation numbers, addresses, check-in/check-out times, flight numbers, ticket links.
- Any member can move a planning item to finalized and attach booking details.
- The bot can produce a full itinerary document from finalized items (see §5).
- The bot answers schedule questions from finalized data (e.g., "what are we doing on Thursday?" or "what time is our flight?").

### 3.4 Stage Transitions

```
Brainstorming  ──→  Planning  ──→  Finalized
     ↑                  ↑               │
     └──────────────────┴───────────────┘
           (items can move backward)
```

- Any group member can command the bot to move items between any stages.
- Moving an item forward curates and structures data progressively.
- Moving an item backward (e.g., finalized → planning) is supported for changes or cancellations.

## 4. Bot Interaction Model

### 4.1 Trigger

The bot responds only when directly addressed:
- **@mention**: Mentioning the bot by its GroupMe name.
- **Trigger keyword**: A configurable keyword/prefix (e.g., `/trip` or `!bot`).

The bot does **not** respond to every message in the group.

### 4.2 Capabilities

| Command Category | Examples |
|---|---|
| **Ask a question** | "What hotels are we considering?" · "What's the schedule for Saturday?" |
| **Add to brainstorming** | "Add snorkeling as an activity idea" · (bot also captures ideas from natural conversation when addressed) |
| **Move between stages** | "Move the Airbnb to planning" · "Finalize the flight — confirmation #ABC123" |
| **Show stage contents** | "Show me everything in planning" · "What's still in brainstorming?" |
| **Generate itinerary** | "Give me a summary" · "Send the full itinerary" |
| **Web search** | "Search for hotels near Tulum under $200/night" · "What's the weather in Costa Rica in March?" |
| **Manage trip** | "Start a new trip to Japan" · "Archive this trip" |

### 4.3 Response Style

- Conversational and concise in chat.
- Context-aware: the bot remembers what stage the group is in and what's been discussed.
- When producing longer outputs (itinerary, stage summaries), uses structured formatting that renders well in GroupMe.

## 5. Itinerary Output

### 5.1 In-Chat Summary

On request, the bot posts a concise day-by-day summary directly in the GroupMe chat. Suitable for a quick glance.

### 5.2 Full Document

On request, the bot generates a formatted itinerary document (PDF or hosted web page) and shares a link in the chat. The full document includes:

- Trip title, dates, and participants
- Day-by-day schedule with times
- All booking details (confirmation numbers, addresses, contact info)
- Any notes or reminders attached to itinerary items

## 6. MVP Scope

### In Scope

- One active trip per GroupMe group
- Three-stage storage (brainstorming / planning / finalized)
- Natural language interaction via Azure OpenAI
- Web search for real-time travel information
- Explicit commands to move items between stages
- Itinerary generation (chat summary + full document)
- Persistent storage across conversations

### Out of Scope (Future Consideration)

- Multiple concurrent trips per group
- User authentication beyond GroupMe identity
- Payment processing or direct booking
- Calendar integration (Google Calendar, Outlook)
- Budget tracking and splitting
- Multi-language support
- Mobile app or web dashboard
