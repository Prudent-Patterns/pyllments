from pydantic import BaseModel, Field, conlist

# ===============================================
# Medium term memory (Temporary context storage)
# ===============================================
class UserPreference(BaseModel):
    """A user preference."""
    name: str = Field(..., description="The name of the preference")
    value: str = Field(..., description="The value of the preference")
    context: str = Field(..., description="Brief description of the context of this preference.")

class UserGoal(BaseModel):
    """A user goal."""
    name: str = Field(..., description="The name of the goal")
    value: str = Field(..., description="The value of the goal")
    context: str = Field(..., description="Brief description of the context of this goal.")

class TaskStep(BaseModel):
    """A task step."""
    name: str = Field(..., description="The name of the step")
    value: str = Field(..., description="The value of the step")
    context: str = Field(..., description="Brief description of the context of this step.")

class Task(BaseModel):
    """A task consisting of steps."""
    name: str = Field(..., description="The name of the task")
    steps: list[TaskStep] = Field(..., description="A list of task steps.")
    context: str = Field(..., description="Brief description of the context of this task.")

class MediumTermMemory(BaseModel):
    """A container for temporary context that shifts over time."""

    user_preferences: list[UserPreference] = Field(..., description="A list of user preferences.")
    user_goals: list[UserGoal] = Field(..., description="A list of user goals.")
    tasks: conlist(Task, max_length=3) = Field(..., description="A rolling task list. Remove the first task if a new one needs to be added")

# ===============================================
# Long term memory (Durable knowledge storage)
# ===============================================

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

# ===============================================
# Factual Memory
# ===============================================

class FactualMemory(BaseModel):
    """Aggregates different kinds of factual memories."""
    medium_term: MediumTermMemory = Field(..., description="A medium-term memory.")
    long_term: LongTermMemory = Field(..., description="A long-term memory.")
