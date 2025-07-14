import os
import logging
from dotenv import load_dotenv
from pydantic import BaseModel
import chainlit as cl
from openai.types.responses import ResponseTextDeltaEvent
from agents import (
    Agent,
    InputGuardrail,
    AsyncOpenAI,
    GuardrailFunctionOutput,
    Runner,
    OpenAIChatCompletionsModel,
    RunConfig
)

# Load environment variables
load_dotenv()
gemini_api_key = os.getenv("GEMINI_API_KEY")
base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Set up logging
logging.basicConfig(level=logging.INFO)

# Safety check
if not gemini_api_key:
    raise ValueError("❌ GEMINI_API_KEY not found in environment variables.")

# API provider
provider = AsyncOpenAI(
    api_key=gemini_api_key,
    base_url=base_url,
)

# Model configuration
model = OpenAIChatCompletionsModel(
    model="gemini-2.0-flash",
    openai_client=provider
)

# Chainlit RunConfig
config = RunConfig(
    model=model,
    model_provider=provider,
    tracing_disabled=True,
)

# Guardrail output schema
class HomeworkOutput(BaseModel):
    is_homework: bool
    reasoning: str

# Guardrail agent
guardrail_agent = Agent(
    name="Guardrail check",
    instructions="Check if the user is asking about homework.",
    output_type=HomeworkOutput,
    model=model,
)

# Guardrail function
async def homework_guardrail(ctx, agent, input_data):
    result = await Runner.run(guardrail_agent, input_data)
    final_output = result.final_output_as(HomeworkOutput)
    
    logging.info(f"Guardrail output: {final_output}")
    
    return GuardrailFunctionOutput(
        output_info=final_output,
        tripwire_triggered=not final_output.is_homework,
    )

# Specialist agents
math_tutor_agent = Agent(
    name="Math Tutor",
    handoff_description="Specialist agent for math questions",
    instructions="You provide help with math problems. Explain your reasoning at each step and include examples.",
)

history_tutor_agent = Agent(
    name="History Tutor",
    handoff_description="Specialist agent for historical questions",
    instructions="You provide assistance with historical queries. Explain important events and context clearly.",
)

# Triage agent with guardrail
triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine which agent to use based on the user's homework question.",
    handoffs=[history_tutor_agent, math_tutor_agent],
    input_guardrails=[InputGuardrail(guardrail_function=homework_guardrail)],
)

# 🚀 Chainlit: On Chat Start
@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])

    await cl.Message(
    content="""
👋 **Welcome to AI Tutor Assistant!**

I can help you with:
- 🧮 **Math Problems**
- 🏛️ **History Questions**
- 📚 Homework Identification (MHI)

🔗 _Powered by [Muhammad Hamza Ismail (MHI)](https://muhammadhamzaismail.vercel.app/)_

_Ask your question below to begin!_
""",
    author="AI Tutor 👨‍🏫",
).send()


# 🚀 On Each Message
@cl.on_message
async def on_message(message: cl.Message):
    history = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})

    msg = cl.Message(content=" ", author="AI Tutor 👨‍🏫")
    await msg.send()

    try:git
        # Step 1: Run guardrail
        guardrail_output = await homework_guardrail(ctx=cl.context, agent=triage_agent, input_data=history)

        if guardrail_output.tripwire_triggered:
            msg.content = "🚫 That question isn't allowed. Please ask only about **Math**, **History**"
            await msg.update()
            return

        # Step 2: Stream agent output
        result = Runner.run_streamed(
            triage_agent,
            input=history,
            run_config=config
        )

        full_output = ""

        async for event in result.stream_events():
            if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                full_output += event.data.delta
                await msg.stream_token(event.data.delta)

        final_output = result.final_output

        if final_output is None or full_output.strip() == "":
            msg.content = "❌ Sorry, I can only help with Math or History questions related to MHI topics."
        else:
            msg.content = full_output
            history.append({"role": "assistant", "content": full_output})

        await msg.update()

    except Exception as e:
        logging.error(f"Exception: {e}")
        msg.content = f"❌ Oops! Something went wrong:\n\n`{str(e)}`"
        await msg.update()
