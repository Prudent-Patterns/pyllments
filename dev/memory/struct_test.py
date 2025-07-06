import panel as pn
from pydantic import BaseModel, Field
from pyllments import flow
from pyllments.elements import LLMChatElement, TextElement


class BiographicalFact(BaseModel):
    """A biographical fact about the user.
    
    This is a fact about the user that is not related to their knowledge or skills, but rather their personal history, preferences, or other non-knowledge-based information.
    """
    name: str = Field(..., min_length=1, description="The name of the fact")
    value: str = Field(..., min_length=1, description="The value of the fact")
    context: str = Field(..., min_length=1, description="Brief description of the context of this fact.")

class InteractionFact(BaseModel):
    """A fact about an interaction with the user."""
    name: str = Field(..., min_length=1, description="The name of the fact")
    value: str = Field(...,  description="The value of the fact")
    context: str = Field(..., description="Brief description of the context of this fact.")

class KnowledgeFact(BaseModel):
    """A fact about the user's knowledge or skills."""
    domain: str = Field(..., description="The domain or area of knowledge (e.g., 'programming', 'mathematics')")
    level: str = Field(..., description="The level of knowledge or skill (e.g., 'proficient', 'advanced')")
    context: str = Field(..., description="Brief description of how this knowledge was determined (e.g., 'user mentioned solving complex equations')")

class OpinionFact(BaseModel):
    """A fact about the user's opinion on a topic."""
    topic: str = Field(..., description="The topic of the opinion (e.g., 'climate change', 'artificial intelligence')")
    stance: str = Field(..., description="The user's stance or opinion (e.g., 'believes it is urgent', 'optimistic about its potential')")
    context: str = Field(..., description="Brief description of the context in which the opinion was expressed (e.g., 'stated during a discussion on tech')")

class LongTermMemory(BaseModel):
    """A durable knowledge entry intended for long-term storage."""
    biographical_facts:  list[BiographicalFact] = Field(..., description="A list of biographical facts about the user.")
    interaction_facts:  list[InteractionFact] = Field(..., description="A list of interaction facts about the user.")
    knowledge_facts:  list[KnowledgeFact] = Field(..., description="A list of knowledge facts about the user.")
    opinion_facts:  list[OpinionFact] = Field(..., description="A list of opinion facts about the user.")


llm_chat_el = LLMChatElement(model_name='gpt-4.1', response_format=LongTermMemory)
text_input_el = TextElement()
text_output_el = TextElement()

text_input_el.ports.message_output > llm_chat_el.ports.messages_emit_input
llm_chat_el.ports.message_output > text_output_el.ports.message_input

@flow
def main():
    return pn.Row(
        text_input_el.create_input_view(),
        text_output_el.create_display_view(),
        width=1300,
        height=900
        )


