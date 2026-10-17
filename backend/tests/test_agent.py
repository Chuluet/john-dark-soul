"""Idioma de las respuestas y formato del contexto del agente (sin Ollama ni Postgres)."""

from langchain_core.documents import Document

from agents.nodes import reject
from agents.prompts import REJECTION_MESSAGES, rejection_message
from agents.utils import detect_language, extract_sources, format_context, language_name, merge_results, expand_names


def test_detect_language_defaults_to_english():
    assert detect_language("Who is Knight Artorias?") == "en"
    assert detect_language("What happened to Lordran after Gwyn linked the fire") == "en"
    assert detect_language("Artorias") == "en"  # solo un nombre: idioma por defecto


def test_detect_language_spanish_with_and_without_accents():
    assert detect_language("¿Quién es Artorias?") == "es"
    assert detect_language("quien es el caballero artorias") == "es"
    assert detect_language("me cuentas sobre la historia de Lothric") == "es"


def test_detect_language_only_spanish_or_english():
    # Solo español e inglés: sin pistas de español, se responde en inglés.
    assert detect_language("quién") == "es"  # empate sin palabras conocidas: la tilde decide
    assert language_name("es") == "Spanish"
    assert language_name("en") == "English"


def test_rejection_follows_the_question_language():
    assert reject({"language": "es"})["answer"] == REJECTION_MESSAGES["es"]
    assert reject({"language": "en"})["answer"] == REJECTION_MESSAGES["en"]


def test_context_and_sources_use_ingest_metadata():
    docs = [
        (Document(page_content="Artorias walked the Abyss.", metadata={
            "title": "Knight Artorias", "juego": "DS1", "seccion": "Lore",
            "fuente": "knight-artorias__DS1.md", "url": "https://wiki/Artorias"}), 0.8),
        (Document(page_content="Second part.", metadata={
            "title": "Knight Artorias", "juego": "DS1", "fuente": "knight-artorias__DS1.md"}), 0.7),
        (Document(page_content="Video part.", metadata={
            "title": "lore", "juego": "general", "seccion": "01:30 - 03:00", "fuente": "lore.mp4"}), 0.6),
    ]

    context = format_context(docs)

    # El modelo cita el archivo, como las fuentes de la interfaz.
    assert "[Fragment 1 | document: knight-artorias__DS1.md]" in context
    assert "[Fragment 3 | document: lore.mp4]" in context
    # La fuente es el archivo que generó los fragmentos, no la página de la wiki.
    assert extract_sources(docs) == [
        {"title": "Knight Artorias", "game": "DS1", "document": "knight-artorias__DS1.md"},
        {"title": "lore", "game": "general", "document": "lore.mp4"},
    ]


def test_citation_word_follows_the_question_language():
    from agents.prompts import citation_word

    assert citation_word("en") == "source"
    assert citation_word("es") == "fuente"
    assert citation_word("xx") == "source"  # idioma desconocido: inglés


def test_proper_nouns_and_known_names():
    from agents.utils import known_names_in, proper_nouns

    names = proper_nouns([
        "Darkeater Midir was raised by the gods. Midir guards the Ringed City.",
        "Slave Knight Gael seeks the dark soul. The black fire burns. Gael fights.",
        "Black Knights wander. A black sword and a black shield.",
    ])

    assert {"midir", "gael"} <= names.keys()
    assert "darkeater" not in names  # sale una sola vez: no basta para saber que es un nombre
    assert "black" not in names and "fire" not in names  # también salen en minúscula
    assert names["midir"] == pytest.approx(1 / 3)  # fracción de textos en que sale
    assert proper_nouns([]) == {}
    assert known_names_in("who is midir", names)
    assert known_names_in("quien es la gael", names)
    assert not known_names_in("How do I cook sushi?", names)
    assert not known_names_in("who is gail", {"gael", "quelaag"})  # palabra corta: sin erratas
    assert known_names_in("who is quelag", {"gael", "quelaag"})          # errata tolerada


def test_rare_names_drop_names_that_are_everywhere():
    from agents.utils import rare_names

    assert rare_names({"dark": 0.7, "souls": 0.68, "gael": 0.01, "artorias": 0.04}) == {"gael", "artorias"}


def test_floor_keeps_low_fragments_that_name_what_is_asked(monkeypatch):
    """'who is gael': el fragmento que nombra a Gael entra aunque quede bajo el umbral."""
    monkeypatch.setattr(nodes, "get_names", lambda: {"gael": 0.01, "dark": 0.7})
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["YES"]))
    monkeypatch.setattr(nodes.config, "SIMILARITY_THRESHOLD", 0.46)
    monkeypatch.setattr(nodes.config, "SIMILARITY_FLOOR", 0.38)
    gael = Document(page_content="Slave Knight Gael seeks the Dark Soul.", metadata={"fuente": "c.md"})
    otro = Document(page_content="The Dark Souls lore is vast.", metadata={"fuente": "d.md"})
    lejos = Document(page_content="Gael again.", metadata={"fuente": "e.md"})

    result = nodes.evaluate_context({"question": "who is gael", "search_query": "Who is Gael in Dark Souls?",
                                     "docs": [(gael, 0.45), (otro, 0.45), (lejos, 0.30)]})

    # 'otro' solo comparte 'dark' (sale en todo); 'lejos' está bajo el piso.
    assert [d.metadata["fuente"] for d, _ in result["docs"]] == ["c.md"]


def test_off_topic_questions_are_still_searched(monkeypatch):
    """Un NO del clasificador no rechaza: se busca con la pregunta original.

    Así se responde lo que el modelo no reconoce como Dark Souls (Midir) o los
    documentos de otros temas que suben los usuarios.
    """
    busquedas = []

    class Busqueda:
        def invoke(self, argumentos):
            busquedas.append(argumentos["query"])
            return [(Document(page_content="Grandma Rosa's ajiaco uses guascas.",
                              metadata={"fuente": "uploads/a/ajiaco.txt"}), 0.7)]

    monkeypatch.setattr(nodes, "search_documents", Busqueda())
    # Una sola instancia: cada llamada al LLM toma la siguiente respuesta.
    llm = FakeListChatModel(responses=["NO", "YES", "It uses guascas (source: ajiaco.txt)."])
    monkeypatch.setattr(nodes, "create_llm", lambda: llm)
    graph = build_graph()
    config = {"configurable": {"thread_id": "ajiaco"}}
    # El estado arrastra el search_query de la pregunta anterior: no se debe reutilizar.
    graph.update_state(config, {"search_query": "Who is Artorias?"})

    result = graph.invoke({"question": "What is in grandma Rosa's ajiaco?"}, config)

    assert busquedas == ["What is in grandma Rosa's ajiaco?"]  # sin reescritura ni consulta vieja
    assert result["rejected"] is False
    assert result["sources"] == [{"title": "uploads/a/ajiaco.txt", "game": None, "document": "ajiaco.txt"}]


def test_a_known_name_gets_the_question_rewritten(monkeypatch):
    """'quien es la gael': aunque el clasificador diga NO, se reescribe (traduce) antes de buscar."""
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["NO"]))
    monkeypatch.setattr(nodes, "get_names", lambda: {"gael": 0.01})

    assert nodes.validate_intent({"question": "quien es la gael"})["on_topic"] is True
    assert nodes.validate_intent({"question": "How do I cook sushi?"})["on_topic"] is False


def test_off_topic_question_without_matches_is_rejected(monkeypatch):
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["NO"]))

    result = build_graph().invoke({"question": "How do I cook sushi?"},
                                  {"configurable": {"thread_id": "sushi"}})

    assert result["rejected"] is True and result["answer"] == REJECTION_MESSAGES["en"]


def test_document_name_drops_folders():
    from agents.utils import document_name

    assert document_name("uploads/0a1b/gael__DS3.pdf") == "gael__DS3.pdf"
    assert document_name("lore\\gael__DS3.md") == "gael__DS3.md"
    assert document_name("abyss__DS1.md") == "abyss__DS1.md"


def _doc(source, fragment=0):
    return Document(page_content=f"{source}-{fragment}", metadata={"fuente": source, "fragmento": fragment})


def test_merge_results_keeps_best_score_and_limits_per_source():
    original = [(_doc("chosen-undead.md", 0), 0.57), (_doc("chosen-undead.md", 1), 0.56), (_doc("sen.md"), 0.55)]
    rewritten = [(_doc("frampt.md"), 0.60), (_doc("chosen-undead.md", 0), 0.59)]

    merged = merge_results([original, rewritten], k=3, max_per_source=1)

    assert [(d.page_content, s) for d, s in merged] == [
        ("frampt.md-0", 0.60), ("chosen-undead.md-0", 0.59), ("sen.md-0", 0.55)]


TITLES = ["Kingseeker Frampt", "Great Grey Wolf Sif", "Chosen Undead", "Abyss", "Abyss Watchers", "Vendrick"]


def test_expand_names_uses_the_only_page_with_that_name():
    assert expand_names("What did Frampt ask the Chosen Undead?", TITLES) ==         "What did Kingseeker Frampt ask the Chosen Undead?"
    assert expand_names("Who is Sif?", TITLES) == "Who is Great Grey Wolf Sif?"


def test_expand_names_leaves_ambiguous_or_complete_names():
    assert expand_names("What is the Abyss?", TITLES) == "What is the Abyss?"          # está en dos títulos
    assert expand_names("Who is Kingseeker Frampt?", TITLES) == "Who is Kingseeker Frampt?"
    assert expand_names("who is frampt", TITLES) == "who is frampt"                    # solo nombres propios


# --- Rechazos decididos por el modelo, fallos de servicio e historial ---------

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from agents import nodes
from agents.graph import build_graph
from agents.prompts import SERVICE_ERROR_MESSAGES
from agents.utils import is_rejection

ARTORIAS = [(Document(page_content="Artorias walked the Abyss.", metadata={
    "title": "Knight Artorias", "juego": "DS1", "fuente": "knight-artorias__DS1.md"}), 0.8)]


class BusquedaVacia:
    """La @tool de búsqueda sin pgvector: no encuentra nada."""

    def invoke(self, argumentos):
        return []


@pytest.fixture(autouse=True)
def sin_postgres(monkeypatch):
    """Las pruebas del grafo no tocan Postgres: búsqueda vacía y sin nombres ni documentos apagados."""
    monkeypatch.setattr(nodes, "get_names", lambda: {})
    monkeypatch.setattr(nodes, "get_titles", lambda: [])
    monkeypatch.setattr(nodes, "search_documents", BusquedaVacia())
    monkeypatch.setattr(nodes.db, "fuentes_desactivadas", lambda user_id: set())


def test_is_rejection_tolerates_quotes_and_missing_suggestion():
    assert is_rejection('"No tengo suficiente información en mi base de conocimiento '
                        'para responder esa pregunta."', REJECTION_MESSAGES.values())
    assert is_rejection(REJECTION_MESSAGES["en"], REJECTION_MESSAGES.values())
    assert not is_rejection("Artorias walked the Abyss (fuente: Knight Artorias, DS1).",
                            REJECTION_MESSAGES.values())


def test_generate_drops_sources_when_the_model_rejects(monkeypatch):
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=[REJECTION_MESSAGES["es"]]))

    result = nodes.generate({"question": "¿Quién mató a Artorias?", "language": "es", "docs": ARTORIAS})

    assert result == {"answer": REJECTION_MESSAGES["es"], "sources": [], "rejected": True}


def test_generate_keeps_sources_when_it_answers(monkeypatch):
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["Artorias walked the Abyss."]))

    result = nodes.generate({"question": "Who is Artorias?", "language": "en", "docs": ARTORIAS})

    assert result["rejected"] is False
    assert result["sources"] == [{"title": "Knight Artorias", "game": "DS1", "document": "knight-artorias__DS1.md"}]


def _ollama_caido():
    def fallar(_):
        raise ConnectionError("Ollama no responde")
    return RunnableLambda(fallar)


def test_graph_returns_error_instead_of_raising_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr(nodes, "create_llm", _ollama_caido)
    guardados = []
    monkeypatch.setattr(nodes.db, "guardar_mensaje", lambda **kw: guardados.append(kw))

    result = build_graph().invoke({"question": "¿Quién es Artorias?", "user_id": "demo"},
                                  {"configurable": {"thread_id": "caido"}})

    assert result["error"] and "ConnectionError" in result["error"]
    assert result["answer"] == SERVICE_ERROR_MESSAGES["es"]
    assert result["sources"] == []
    assert guardados == []  # un fallo de servicio no es historial


def test_error_does_not_leak_into_the_next_question_of_the_same_thread(monkeypatch):
    graph = build_graph()
    config = {"configurable": {"thread_id": "misma-sesion"}}
    monkeypatch.setattr(nodes, "create_llm", _ollama_caido)
    graph.invoke({"question": "Who is Artorias?"}, config)

    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["NO"]))
    result = graph.invoke({"question": "How do I cook sushi?"}, config)

    assert result["error"] is None
    assert result["answer"] == REJECTION_MESSAGES["en"]


def test_save_history_stores_answers_and_rejections(monkeypatch):
    guardados = []
    monkeypatch.setattr(nodes.db, "guardar_mensaje", lambda **kw: guardados.append(kw))
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["NO"]))

    result = build_graph().invoke(
        {"question": "How do I cook sushi?", "user_id": "demo", "session_id": "chat-1"},
        {"configurable": {"thread_id": "historial"}})

    assert result["rejected"] is True
    assert guardados == [{"user_id": "demo", "session_id": "chat-1", "question": "How do I cook sushi?",
                          "answer": REJECTION_MESSAGES["en"], "sources": [], "rejected": True}]


def test_retrieve_skips_the_documents_the_user_disabled(monkeypatch):
    pedidos = []

    class ToolFalsa:
        def invoke(self, argumentos):
            pedidos.append(argumentos)
            return ARTORIAS

    monkeypatch.setattr(nodes, "search_documents", ToolFalsa())
    monkeypatch.setattr(nodes.db, "fuentes_desactivadas", lambda user_id: {"abyss__DS1.md", "sif__DS1.md"})

    nodes.retrieve({"question": "Who is Artorias?", "user_id": "demo"})
    assert pedidos[0]["excluded"] == ["abyss__DS1.md", "sif__DS1.md"]

    # Sin usuario (pruebas por consola) no se consulta la tabla.
    pedidos.clear()
    nodes.retrieve({"question": "Who is Artorias?"})
    assert pedidos[0]["excluded"] == []


def test_retrieve_reports_db_errors_reading_disabled_documents(monkeypatch):
    def db_caida(user_id):
        raise ConnectionError("Postgres no responde")
    monkeypatch.setattr(nodes.db, "fuentes_desactivadas", db_caida)

    result = nodes.retrieve({"question": "Who is Artorias?", "user_id": "demo"})

    assert result["docs"] == [] and "ConnectionError" in result["error"]


def test_saved_history_seeds_a_session_the_checkpointer_forgot(monkeypatch):
    """Una conversación retomada tras reiniciar recibe sus mensajes previos en {history}."""
    from langchain_core.messages import AIMessage, HumanMessage
    from agents.graph import ask, has_memory

    vistos = []

    def llm_que_registra(prompt):
        vistos.append(prompt.to_string())
        return "NO"

    monkeypatch.setattr(nodes, "create_llm", lambda: RunnableLambda(llm_que_registra))
    graph = build_graph()
    assert not has_memory(graph, "retomada")

    ask(graph, "And his wolf?", "retomada",
        history=[HumanMessage("Who is Artorias?"), AIMessage("A knight of Gwyn.")])

    assert "User: Who is Artorias?" in vistos[-1]
    assert has_memory(graph, "retomada")


def test_save_history_skips_without_user_and_survives_db_errors(monkeypatch):
    def db_caida(**_):
        raise ConnectionError("Postgres no responde")
    monkeypatch.setattr(nodes.db, "guardar_mensaje", db_caida)
    estado = {"question": "q", "answer": "a", "sources": [], "rejected": False}

    # Sin user_id no intenta guardar en la tabla, y con Postgres caído no revienta;
    # en ambos casos la interacción sí queda en la memoria de la sesión.
    for resultado in (nodes.save_history(estado), nodes.save_history(estado | {"user_id": "demo"})):
        assert [m.content for m in resultado["messages"]] == ["q", "a"]


def test_memory_follow_up_question_sees_the_previous_turn(monkeypatch):
    """La segunda pregunta de la sesión recibe la primera en {history}."""
    vistos = []

    def llm_que_registra(prompt):
        vistos.append(prompt.to_string())
        return "NO"

    monkeypatch.setattr(nodes, "create_llm", lambda: RunnableLambda(llm_que_registra))
    graph = build_graph()
    config = {"configurable": {"thread_id": "memoria"}}
    graph.invoke({"question": "Who is Artorias?"}, config)
    result = graph.invoke({"question": "And his wolf?"}, config)

    assert "User: Who is Artorias?" in vistos[-1]
    assert len(result["messages"]) == 4  # 2 preguntas + 2 respuestas


def test_format_history_keeps_last_turns_and_trims():
    from langchain_core.messages import AIMessage, HumanMessage
    from agents.utils import format_history

    mensajes = [HumanMessage(f"q{i}") if i % 2 == 0 else AIMessage("x" * 500) for i in range(10)]
    texto = format_history(mensajes, max_turns=2, max_chars=100)

    assert texto.count("User:") == 2 and texto.count("Assistant:") == 2
    assert "x" * 101 not in texto
    assert format_history([]) == "(no previous messages)"


def test_format_history_skips_rejections():
    from langchain_core.messages import AIMessage, HumanMessage
    from agents.utils import format_history

    texto = format_history([HumanMessage("Who is Artorias?"), AIMessage("A knight of Gwyn."),
                            HumanMessage("What happened to his shield?"), AIMessage(REJECTION_MESSAGES["en"])])

    assert texto == "User: Who is Artorias?\nAssistant: A knight of Gwyn.\nUser: What happened to his shield?"
