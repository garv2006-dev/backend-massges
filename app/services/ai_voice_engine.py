import json
import logging
import random
from typing import Dict, Any, List, Optional
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from app.config import settings

logger = logging.getLogger(__name__)

class AIVoiceEngine:
    """
    Intelligent AI Voice & Conversational Engine.
    Handles dynamic multi-turn phone call dialogue generation,
    live interactive conversation turns, sentiment analysis, and outcome extraction.
    """

    @staticmethod
    async def generate_call_dialogue(
        campaign_name: str,
        agent_prompt: Optional[str],
        provider_config: Optional[Dict[str, Any]],
        contact_name: Optional[str] = "Valued Customer",
        contact_phone: Optional[str] = "",
        custom_fields: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a realistic, contextual multi-turn conversation between the AI Voice Agent and the Contact.
        """
        cfg = provider_config or {}
        company_name = cfg.get("company_name", "Apex Solutions")
        agent_name = cfg.get("agent_name", "Sarah")
        tone = cfg.get("tone", "friendly and professional")
        language = cfg.get("language", "English")
        opening_line = cfg.get("opening_line") or f"Hello! Am I speaking with {contact_name}? This is {agent_name} calling from {company_name}."
        prompt_instructions = agent_prompt or "Inquire about customer satisfaction, answer queries, and discuss potential collaboration."

        # Try generating via Gemini API first if configured
        if genai and settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your-"):
            try:
                system_instruction = f"""
You are an advanced AI calling agent simulator. Generate a realistic multi-turn voice phone call between:
AI Agent: {agent_name} representing {company_name} (Tone: {tone}, Language: {language})
Contact: {contact_name} (Phone: {contact_phone})

Campaign Objective & Script:
{prompt_instructions}

Opening Line:
"{opening_line}"

Produce a natural, realistic phone conversation of 3 to 6 dialogue turns.
Also analyze the conversation and return ONLY a valid JSON object formatted as:
{{
  "dialogue": [
    {{"speaker": "agent", "text": "...", "timestamp": "00:02"}},
    {{"speaker": "contact", "text": "...", "timestamp": "00:06"}},
    {{"speaker": "agent", "text": "...", "timestamp": "00:12"}},
    {{"speaker": "contact", "text": "...", "timestamp": "00:18"}},
    {{"speaker": "agent", "text": "...", "timestamp": "00:25"}}
  ],
  "duration_seconds": 35,
  "sentiment": "positive",
  "customer_intent": "Interested in product demo",
  "customer_rating": 5,
  "complaint": null,
  "follow_up_required": "yes",
  "follow_up_notes": "Customer requested detailed brochure via WhatsApp/Email.",
  "call_outcome": "Lead Qualified",
  "summary": "Customer expressed interest and agreed to follow up next Tuesday."
}}
"""
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = None
                for model_name in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]:
                    try:
                        response = await client.aio.models.generate_content(
                            model=model_name,
                            contents=system_instruction
                        )
                        if response and response.text:
                            break
                    except Exception:
                        continue

                if response and response.text:
                    raw_text = response.text.strip()
                    if "```json" in raw_text:
                        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw_text:
                        raw_text = raw_text.split("```")[1].split("```")[0].strip()
                    parsed = json.loads(raw_text)
                    if "dialogue" in parsed and isinstance(parsed["dialogue"], list):
                        return parsed
            except Exception as e:
                logger.warning(f"Gemini generation fallback triggered: {e}")

        # Intelligent Dynamic Fallback Generator tailored to language & tone
        return AIVoiceEngine._generate_contextual_fallback(
            company_name=company_name,
            agent_name=agent_name,
            contact_name=contact_name or "Valued Customer",
            opening_line=opening_line,
            prompt_instructions=prompt_instructions,
            language=language,
            tone=tone
        )

    @staticmethod
    def _generate_contextual_fallback(
        company_name: str,
        agent_name: str,
        contact_name: str,
        opening_line: str,
        prompt_instructions: str,
        language: str,
        tone: str
    ) -> Dict[str, Any]:
        """
        Rich, dynamic dialogue simulation generator supporting Gujarati, Hindi, English, and Hinglish.
        """
        lang_lower = language.lower()
        duration = random.randint(28, 65)

        if "gujarat" in lang_lower:
            dialogue = [
                {"speaker": "agent", "text": f"નમસ્તે {contact_name} જી, હું {company_name} માંથી {agent_name} વાત કરું છું. કેમ છો?", "timestamp": "00:02"},
                {"speaker": "contact", "text": "નમસ્તે, હા બોલો, શું કામ હતું?", "timestamp": "00:07"},
                {"speaker": "agent", "text": f"અમે અમારા ખાસ ગ્રાહકો માટે નવી સર્વિસ અને ઑફર્સ લાવ્યા છીએ. શું હું તમારી 2 મિનિટ લઈ શકું?", "timestamp": "00:14"},
                {"speaker": "contact", "text": "હા ચોક્કસ, મને વધુ વિગત આપો.", "timestamp": "00:20"},
                {"speaker": "agent", "text": f"આભાર! અમે તમને પૂરી વિગતો WhatsApp અને Email પર મોકલી આપીશું. તમારો દિવસ સારો રહે!", "timestamp": "00:28"},
                {"speaker": "contact", "text": "બરાબર છે, આભાર!", "timestamp": "00:34"}
            ]
            summary = f"{contact_name} સાથે ગુજરાતીમાં વાતચીત સફળ રહી. વિગતો મોકલવાની સંમતિ આપી."
            intent = "વિગતો મેળવવામાં રસ ધરાવે છે"
            notes = "WhatsApp પર માહિતી મોકલવી."
        elif "hindi" in lang_lower or "hinglish" in lang_lower:
            dialogue = [
                {"speaker": "agent", "text": f"नमस्ते {contact_name} जी, मैं {company_name} से {agent_name} बात कर रही हूँ। क्या मेरी बात {contact_name} जी से हो रही है?", "timestamp": "00:02"},
                {"speaker": "contact", "text": "हाँ जी, मैं ही बात कर रहा हूँ। बताइए?", "timestamp": "00:08"},
                {"speaker": "agent", "text": f"बहुत बढ़िया! मैं आपको हमारे नए समाधान और विशेष लाभ के बारे में संक्षिप्त जानकारी देने के लिए कॉल कर रही थी। क्या यह सही समय है बात करने का?", "timestamp": "00:15"},
                {"speaker": "contact", "text": "हाँ, कृपया बताइए यह कैसे काम करता है?", "timestamp": "00:23"},
                {"speaker": "agent", "text": f"बिल्कुल! हमारी सेवा आपके काम को 50% आसान और तेज़ बनाती है। मैं आपको एक संक्षिप्त डेमो लिंक और ब्रोशर भेज देती हूँ।", "timestamp": "00:31"},
                {"speaker": "contact", "text": "ठीक है, आप मुझे डिटेल्स भेज दीजिए, मैं चेक कर लूँगा।", "timestamp": "00:39"},
                {"speaker": "agent", "text": f"धन्यवाद {contact_name} जी! आपका दिन शुभ रहे।", "timestamp": "00:45"}
            ]
            summary = f"{contact_name} से सकारात्मक बातचीत हुई। उन्होंने डेमो लिंक और डिटेल्स भेजने का अनुरोध किया।"
            intent = "डेमो और सर्विस में रुचि"
            notes = "WhatsApp/Email पर डिटेल्स और लिंक भेजें।"
        else:
            dialogue = [
                {"speaker": "agent", "text": opening_line.replace("{name}", contact_name).replace("{agent_name}", agent_name).replace("{company_name}", company_name), "timestamp": "00:02"},
                {"speaker": "contact", "text": f"Hello {agent_name}, yes speaking. How can I help you?", "timestamp": "00:07"},
                {"speaker": "agent", "text": f"Glad to reach you, {contact_name}! I'm reaching out regarding our latest updates at {company_name} to see how we can assist your workflow.", "timestamp": "00:14"},
                {"speaker": "contact", "text": "That sounds interesting. Could you share a quick overview of what you offer?", "timestamp": "00:22"},
                {"speaker": "agent", "text": f"Certainly! We help streamline your voice outreach and operations with 100% automated AI intelligence. I'd love to send you a customized summary.", "timestamp": "00:32"},
                {"speaker": "contact", "text": "Sounds great! Please email me the details, and I will review them.", "timestamp": "00:40"},
                {"speaker": "agent", "text": f"Fantastic! I'll dispatch that right away. Have a wonderful day ahead, {contact_name}!", "timestamp": "00:48"}
            ]
            summary = f"Engaged with {contact_name}. Customer showed high interest in the offering and requested detailed documentation."
            intent = "Interested in Product & Follow-up"
            notes = "Send follow-up documentation and schedule a demo."

        return {
            "dialogue": dialogue,
            "duration_seconds": duration,
            "sentiment": random.choice(["positive", "positive", "neutral", "positive"]),
            "customer_intent": intent,
            "customer_rating": random.choice([5, 4, 5]),
            "complaint": None,
            "follow_up_required": "yes",
            "follow_up_notes": notes,
            "call_outcome": "Completed - Interested",
            "summary": summary
        }

    @staticmethod
    async def generate_live_turn(
        campaign_name: str,
        agent_prompt: Optional[str],
        provider_config: Optional[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
        user_message: str,
        contact_name: Optional[str] = "Customer"
    ) -> str:
        """
        Generate real-time response for in-browser live AI voice simulator.
        """
        cfg = provider_config or {}
        company_name = cfg.get("company_name", "Apex Solutions")
        agent_name = cfg.get("agent_name", "Sarah")
        tone = cfg.get("tone", "friendly and professional")
        language = cfg.get("language", "English")
        instructions = agent_prompt or "Help the customer politely, answer questions, and explain our services."

        if genai and settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your-"):
            try:
                system_prompt = f"""You are {agent_name}, a friendly, courteous, and professional human team representative for {company_name} chatting with a customer on WhatsApp.
Tone: {tone}
Language: {language}
Business Context & Guidelines:
{instructions}

Customer Name: {contact_name}

CRITICAL COMMUNICATION RULES:
1. Act 100% as a real human. NEVER mention you are an AI, bot, language model, automated system, or virtual assistant.
2. Reply in 1-2 natural, polite, and helpful sentences directly addressing what the customer said.
3. If the customer sent a simple greeting like "hi", "hello", "hey", or "good morning", greet them back warmly by name and politely ask how you can help them today regarding {company_name}.
4. If the customer asks about pricing, packages, or details, acknowledge enthusiastically and offer the next step (e.g. sharing details right here or setting up a short demo).
5. If the customer replies in Hindi, Hinglish, or Gujarati, match their language naturally.
6. Keep messages clean, concise, and friendly. Do not use robotic jargon, system disclaimers, or awkward formal templates.
"""
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                
                # Build chat history
                history_text = "\n".join([f"{turn.get('speaker', 'user')}: {turn.get('text', '')}" for turn in conversation_history])
                prompt = f"Chat History:\n{history_text}\nCustomer just messaged: \"{user_message}\"\nYour response as {agent_name}:"
                
                config = types.GenerateContentConfig(system_instruction=system_prompt) if types else None
                response = None
                for candidate_model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                    try:
                        response = await client.aio.models.generate_content(
                            model=candidate_model,
                            contents=prompt,
                            config=config
                        )
                        if response and response.text:
                            return response.text.strip()
                    except Exception as model_err:
                        logger.debug(f"Model {candidate_model} notice: {model_err}")
                        continue
            except Exception as e:
                logger.warning(f"Gemini live turn failed, using fallback: {e}")

        # Intelligent conversational fallback response logic
        msg_lower = user_message.lower().strip()
        
        # Gujarati handling
        if "gujarat" in language.lower():
            if any(w in msg_lower for w in ["hi", "hello", "hey", "નમસ્તે", "કેમ છો", "હેલો"]):
                return f"નમસ્તે {contact_name} જી! કેમ છો? હું {company_name} તરફથી તમારી શું મદદ કરી શકું?"
            if any(w in msg_lower for w in ["હા", "હાજી", "yes", "વિગત", "માહિતી", "details", "ભાવ", "price"]):
                return f"ચોક્કસ {contact_name} જી, અમે તમને બધી વિગતો મોકલી આપીશું. શું તમને કોઈ ચોક્કસ સેવા અંગે પૂછપરછ છે?"
            if any(w in msg_lower for w in ["ના", "no", "પછી", "busy"]):
                return f"સમજી ગયો {contact_name} જી, અમે તમને અનુકૂળ સમયે ફરીથી સંપર્ક કરીશું. આભાર!"
            return f"ખૂબ આભાર {contact_name} જી. {company_name} તરફથી અમે તમને શ્રેષ્ઠ સેવા આપીશું!"

        # Hindi / Hinglish handling
        if "hindi" in language.lower() or any(w in msg_lower for w in ["namaste", "kaise", "batao", "kya", "shukriya"]):
            if any(w in msg_lower for w in ["hi", "hello", "hey", "नमस्ते", "नमस्कार", "हेलो", "हाय"]):
                return f"नमस्ते {contact_name} जी! कैसे हैं आप? मैं {company_name} की तरफ से आपकी क्या सहायता कर सकती हूँ?"
            if any(w in msg_lower for w in ["हाँ", "yes", "बताओ", "डिटेल्स", "price", "demo", "rate", "cost"]):
                return f"जी बिल्कुल {contact_name} जी! हमारे पास कई बेहतरीन पैकेजेस हैं। क्या मैं आपको यहाँ पूरी डिटेल्स शेयर कर दूँ?"
            if any(w in msg_lower for w in ["नहीं", "no", "बाद में", "busy", "kal"]):
                return f"कोई बात नहीं {contact_name} जी, आप जब भी फ्री हों मुझे बता दीजिएगा। आपका दिन शुभ रहे!"
            return f"धन्यवाद {contact_name} जी! {company_name} की तरफ से हम आपकी पूरी सहायता के लिए हमेशा तैयार हैं।"

        # English handling
        # 1. Greetings ("hi", "hello", "hey")
        if any(msg_lower == w or msg_lower.startswith(w + " ") for w in ["hi", "hello", "hey", "hola", "good morning", "good afternoon", "good evening"]):
            return f"Hello {contact_name}! Great to connect with you. How can I help you today regarding {company_name}?"

        # 2. Interest / Pricing / Details
        if any(w in msg_lower for w in ["yes", "sure", "tell me", "details", "cost", "price", "demo", "interested", "info", "package"]):
            return f"That sounds wonderful, {contact_name}! We offer tailored plans designed for your needs. Would you like me to share our full overview right here, or arrange a quick 5-minute call?"

        # 3. Busy / Not interested
        if any(w in msg_lower for w in ["no", "not now", "busy", "later", "call back", "stop", "unsubscribe"]):
            return f"I completely understand, {contact_name}. Thank you for letting me know, and feel free to reach out anytime when it's convenient for you!"

        # 4. Identity / Who is this?
        if any(w in msg_lower for w in ["who", "what", "which company", "explain", "koun"]):
            return f"This is {agent_name} from {company_name}. We reached out regarding our services to see how we could assist you. How can I best help you today?"

        return f"Thank you for reaching out, {contact_name}! How may I assist you with {company_name} today?"
