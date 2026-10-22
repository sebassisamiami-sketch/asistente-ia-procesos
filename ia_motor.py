# ia_motor.py 
"""
Motor IA centralizado para ProcesosIAEngine v2.0
Implementa patrón Singleton con inicialización robusta y prevención de alucinaciones
"""

import logging
import os
import json
import re
import unicodedata
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.memory import ConversationBufferMemory
from langchain_community.vectorstores import Chroma
from langchain.chains import ConversationalRetrievalChain
from langchain.schema import HumanMessage, AIMessage
from langchain.prompts import PromptTemplate

logger = logging.getLogger(__name__)

# Conocimiento general (modo experto) para preguntas conceptuales.
# Respeta los manuales: para PROCEDIMIENTOS específicos se usa la documentación (RAG);
# esto solo cubre EXPLICAR conceptos del dominio.
EXPERTO_SYS = (
    "Eres un experto técnico y desarrollador senior en procesos BPM (Business Process Management), "
    "en plataformas de BPM e integración, en gestores de tickets y en los "
    "procesos de atención de solicitudes y facturación de Andina Servicios. Combinas el rol de analista de procesos con el "
    "de desarrollador: además de explicar conceptos, sabes orientar cuando un caso requiere "
    "DESARROLLO o MODIFICACIÓN que no está documentado en los manuales.\n"
    "Explica de forma clara, didáctica y profesional, con ejemplos sencillos.\n"
    "\n"
    "Contexto del negocio: en Andina Servicios los tickets/casos se gestionan y validan en flujos "
    "de BPM y se RESUELVEN en el gestor de tickets (donde se consultan los casos).\n"
    "\n"
    "Herramientas de desarrollo que usa el equipo (tenlas en cuenta al recomendar soluciones):\n"
    "- Plataforma BPM e integración. "
    "Se usa su diseñador para crear/editar servicios, "
    "flujos de procesos (BPM), conectores, mapeos y validaciones.\n"
    "- DBeaver: cliente de base de datos para ejecutar y revisar consultas SQL, inspeccionar "
    "tablas y validar datos de los casos.\n"
    "- Gestor de tickets: donde se consultan, hacen seguimiento y cierran los "
    "tickets/casos.\n"
    "\n"
    "Tipos de flujo de BPM que debes conocer y saber explicar:\n"
    "- Flujo principal y subflujos (procesos y subprocesos anidados).\n"
    "- Etapas/estados del flujo y las transiciones entre ellos.\n"
    "- Validaciones, reglas de negocio y puntos de decisión (gateways).\n"
    "- Reasignación de tareas y manejo de excepciones/errores.\n"
    "- Instancias padre e instancias hijo (procesos relacionados).\n"
    "- Cierre del caso y la integración con el gestor de tickets.\n"
    "\n"
    "Reglas:\n"
    "- Puedes usar conocimiento general del tema para EXPLICAR conceptos y para ORIENTAR "
    "desarrollos o modificaciones (qué herramienta usar, qué tipo de servicio/flujo tocar, "
    "qué pasos lógicos seguir, qué validar en BD con DBeaver, etc.).\n"
    "- Cuando el analista pregunte por algo que NECESITA desarrollo o modificación y NO esté en el "
    "manual, dale una guía práctica: el enfoque recomendado, en qué herramienta hacerlo "
    "(diseñador de la plataforma BPM, DBeaver o gestor de tickets) y qué tener en cuenta del flujo de BPM.\n"
    "- NO inventes identificadores, nombres de servicios, tablas, columnas ni consultas SQL "
    "exactas; si no los conoces, descríbelos de forma genérica e indica que se validen en el "
    "entorno real (diseñador BPM/DBeaver) o con el responsable técnico.\n"
    "- Para PROCEDIMIENTOS o pasos específicos de un caso ya documentado, usa la documentación "
    "interna si se incluye, y si el detalle no está, indica que se consulte el manual del caso.\n"
    "- Responde en español, directo y sin saludos."
)


def _unir_chunks(chunks_text, titulo=None):
    """Reconstruye el texto completo del documento a partir de sus fragmentos,
    quitando el solapamiento (overlap) entre fragmentos consecutivos y la
    cabecera '[Documento: ...]' repetida. Así la fuente se ve completa y limpia."""
    limpios = []
    for t in chunks_text:
        t = t or ""
        # quitar la cabecera '[Documento: titulo]\n' que se antepone a cada chunk
        if t.startswith("[Documento:"):
            nl = t.find("\n")
            if nl != -1:
                t = t[nl + 1:]
        limpios.append(t)

    full = ""
    for c in limpios:
        if not full:
            full = c
            continue
        # buscar el mayor solapamiento entre el final de 'full' y el inicio de 'c'
        max_ov = min(len(full), len(c), 500)
        ov = 0
        for k in range(max_ov, 15, -1):
            if full[-k:] == c[:k]:
                ov = k
                break
        full += c[ov:]

    full = full.strip()
    if titulo:
        full = f"[Documento: {titulo}]\n{full}"
    return full


class ProcesosIAEngine:
    """
    Motor IA de Andina Servicios - Singleton Pattern
    Gestiona interacción con OpenAI y vectorstore
    """
    
    _instancia = None
    _inicializado = False
    
    def __new__(cls):
        """Implementar patrón Singleton"""
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
        return cls._instancia
    
    def __init__(self):
        """Inicialización segura con verificaciones"""
        if ProcesosIAEngine._inicializado:
            return
        
        logger.info("🚀 Inicializando ProcesosIAEngine...")
        
        # Validar API Key
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "❌ OPENAI_API_KEY no encontrada en .env\n"
                "Por favor crea archivo .env con: OPENAI_API_KEY=sk-..."
            )
        
        logger.info(f"✅ API Key detectada: {self.api_key[:20]}...")
        
        # Inicializar componentes
        self.embeddings = None
        self.vectorstore = None
        self.llm = None
        self.memory = None
        self.chain = None
        self.prompt_str = ""
        self.estado = "inicializando"
        self.estadisticas = {
            "queries_totales": 0,
            "queries_exitosas": 0,
            "queries_fallidas": 0,
            "tokens_usados": 0,
            "ultima_consulta": None
        }
        
        # Crear componentes
        try:
            self._crear_embeddings()
            self._cargar_vectorstore()
            self._crear_llm()
            self._crear_memoria()
            self._crear_cadena()
            
            self.estado = "listo"
            ProcesosIAEngine._inicializado = True
            logger.info("✅ ProcesosIAEngine inicializado correctamente")
        
        except Exception as e:
            self.estado = "error"
            logger.error(f"❌ Error en inicialización: {e}", exc_info=True)
            raise
    
    def _crear_embeddings(self):
        """Crear embeddings de OpenAI"""
        logger.info("🔄 Creando embeddings...")
        try:
            from langchain.embeddings import OpenAIEmbeddings
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=self.api_key
            )
            logger.info("✅ Embeddings creados")
        except Exception as e:
            logger.error(f"❌ Error creando embeddings: {e}")
            raise
    
    def _cargar_vectorstore(self):
        """Cargar o crear vectorstore"""
        logger.info("🔄 Cargando vectorstore...")
        try:
            db_path = "data/db/chroma_db"
            Path(db_path).mkdir(parents=True, exist_ok=True)
            
            self.vectorstore = Chroma(
                persist_directory=db_path,
                embedding_function=self.embeddings,
                collection_name="documentos_procesos"
            )
            
            doc_count = self.vectorstore._collection.count()
            logger.info(f"✅ Vectorstore cargado ({doc_count} documentos)")
        
        except Exception as e:
            logger.error(f"⚠️ Error cargando vectorstore: {e}")
            self.vectorstore = None
    
    def _crear_llm(self):
        """Crear instancia de GPT-4o-mini"""
        logger.info("🔄 Creando LLM...")
        try:
            import openai
            openai.api_key = self.api_key
            
            self.llm = ChatOpenAI(
                openai_api_key=self.api_key,
                model_name="gpt-3.5-turbo",
                temperature=0.0,
                max_tokens=2048,  # Respuestas mas completas
                request_timeout=90
            )
            logger.info("✅ LLM creado")
        except Exception as e:
            logger.error(f"❌ Error creando LLM: {e}")
            raise
    
    def _crear_memoria(self):
        """Crear memoria de conversación"""
        logger.info("🔄 Creando memoria...")
        try:
            self.memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                output_key="answer",
                human_prefix="Usuario",
                ai_prefix="Asistente"
            )
            logger.info("✅ Memoria creada")
        except Exception as e:
            logger.error(f"❌ Error creando memoria: {e}")
            raise
    
    def _crear_cadena(self):
        """Crear cadena de conversación con Prompt Corporativo Estricto"""
        logger.info("🔄 Creando cadena...")
        try:
            if self.vectorstore and self.llm:
                # 🚨 Prompt personalizado para evitar alucinaciones
                prompt_template = """Eres un Consultor y Analista de Procesos Senior en Andina Servicios.
Responde la consulta del usuario utilizando la documentación interna que aparece abajo.

Contexto operativo (úsalo SOLO para ENTENDER la consulta, NO para inventar pasos):
- El equipo trabaja con la plataforma BPM y flujos de BPM (Business Process Management).
- Los tickets/casos se buscan y validan en los flujos de BPM y se RESUELVEN en el gestor de tickets.
- Un caso suele implicar: identificar el ticket, validar la etapa del flujo de BPM, ejecutar acciones y resolverlo en el gestor de tickets.
Importante: la RESPUESTA debe basarse EXCLUSIVAMENTE en la documentación de abajo; este contexto es solo para interpretar mejor la pregunta.

Instrucciones:
- Construye una respuesta clara, completa y bien estructurada (pasos numerados, negritas y, si aparecen en el texto, las consultas SQL exactas).
- Usa la información de los documentos aunque sea parcial; siempre ofrece la mejor respuesta posible con lo que haya disponible. NO te disculpes ni digas que no encontraste el procedimiento.
- No inventes datos, pasos ni consultas que no aparezcan en la documentación.
- Responde directamente, sin saludos ("Hola") ni despedidas.

Documentación interna:
{context}

Consulta: {question}

Respuesta:"""
                
                self.prompt_str = prompt_template
                PROMPT = PromptTemplate(
                    template=prompt_template, input_variables=["context", "question"]
                )

                self.chain = ConversationalRetrievalChain.from_llm(
                    llm=self.llm,
                    retriever=self.vectorstore.as_retriever(search_kwargs={"k": 3}),  # Reducido de 6 a 3
                    memory=self.memory,
                    return_source_documents=True,
                    combine_docs_chain_kwargs={"prompt": PROMPT},
                    verbose=False,
                    get_chat_history=lambda h: h
                )
                logger.info("✅ Cadena con retriever y prompt corporativo estricto creada")
            else:
                logger.warning("⚠️ Cadena sin retriever (no hay vectorstore)")
                self.chain = None
        
        except Exception as e:
            logger.error(f"❌ Error creando cadena: {e}")
            self.chain = None
    
    def query(self, pregunta: str, contexto: Dict = None) -> Dict[str, Any]:
        """Ejecutar query al motor IA.

        - No mezcla casos: cada respuesta usa SOLO el documento elegido.
        - Continuidad: ante preguntas de seguimiento ("paso a paso", "mas detalle"),
          mantiene el caso anterior en lugar de saltar a otro documento.
        """
        try:
            if self.estado != "listo":
                return {
                    'exito': False,
                    'respuesta': "❌ Sistema no inicializado. Por favor recarga la página.",
                    'sources': [],
                    'error': "SISTEMA_NO_LISTO",
                    'timestamp': datetime.now().isoformat()
                }

            # Sin vectorstore -> LLM directo (fallback)
            if not self.vectorstore:
                logger.warning("⚠️ Vectorstore no disponible, usando LLM directo")
                respuesta_llm = self.llm.invoke([HumanMessage(content=pregunta)])
                self.estadisticas['queries_exitosas'] += 1
                return {
                    'exito': True,
                    'respuesta': respuesta_llm.content,
                    'sources': [],
                    'modo': 'LLM_DIRECTO',
                    'timestamp': datetime.now().isoformat()
                }

            logger.info(f"🔍 Query: {pregunta[:100]}...")

            # 1) Recuperar documentos relevantes (con score de distancia)
            try:
                docs_scored = self.vectorstore.similarity_search_with_score(pregunta, k=6)
            except Exception:
                docs_scored = [(d, 0.0) for d in self.vectorstore.similarity_search(pregunta, k=6)]
            docs = [d for d, _ in docs_scored]
            best_score = docs_scored[0][1] if docs_scored else None
            logger.info(f"🔎 Mejor distancia: {best_score}")

            self.estadisticas['queries_totales'] += 1
            self.estadisticas['ultima_consulta'] = datetime.now().isoformat()

            # 2) Normalizacion + deteccion de pregunta de seguimiento
            def _norm(s):
                s = unicodedata.normalize('NFD', str(s).lower())
                return ''.join(c for c in s if unicodedata.category(c) != 'Mn')

            q_norm = _norm(pregunta)
            STOP = {"como", "el", "la", "los", "las", "de", "del", "en", "un",
                    "una", "para", "que", "y", "o", "con", "se", "su", "al",
                    "por", "mi", "es", "cual", "cuales", "hacer", "puedo"}

            ultima_fuente = (contexto or {}).get('ultima_fuente')
            followup_kw = [
                "paso a paso", "pasos", "detalle", "detalla", "explica", "explicame",
                "continua", "amplia", "mas informacion", "mas detalle", "ejemplo",
                "y luego", "entonces", "completo", "resumen", "dime mas", "mas pasos",
                "y como", "ese caso", "lo anterior"
            ]
            es_followup = any(k in q_norm for k in followup_kw)

            # 2.5) MODO EXPERTO (activado/desactivado por el usuario con el botón del chat)
            if (contexto or {}).get('modo_experto'):
                ctx_exp = ""
                try:
                    ctx_exp = "\n\n".join(d.page_content for d in docs[:3])
                except Exception:
                    ctx_exp = ""
                prompt_exp = (
                    EXPERTO_SYS
                    + "\n\nDocumentación interna (úsala si es pertinente):\n"
                    + (ctx_exp[:6000] if ctx_exp else "(sin documentación específica)")
                    + f"\n\nPregunta: {pregunta}\n\nRespuesta:"
                )
                try:
                    resp_exp = self.llm.invoke([HumanMessage(content=prompt_exp)])
                    txt_exp = getattr(resp_exp, "content", str(resp_exp))
                except Exception as e:
                    logger.error(f"Error modo experto: {e}")
                    txt_exp = "No pude generar la explicación en este momento."
                self.estadisticas['queries_exitosas'] += 1
                logger.info("🎓 Modo experto (pregunta conceptual)")
                return {
                    'exito': True,
                    'respuesta': txt_exp,
                    'sources': [],
                    'fuente': None,
                    'modo': 'EXPERTO',
                    'timestamp': datetime.now().isoformat()
                }

            # 3) Mapa de fuentes/titulos del retrieval + re-ranking por titulo
            orden_fuentes = []
            titulo_por_fuente = {}
            for d in docs:
                src = d.metadata.get('source')
                if src and src not in titulo_por_fuente:
                    titulo_por_fuente[src] = d.metadata.get('titulo') or src
                    orden_fuentes.append(src)

            def _title_score(src):
                titulo = _norm(titulo_por_fuente.get(src, src))
                palabras = [w for w in re.findall(r"\w+", titulo)
                            if len(w) > 3 and w not in STOP]
                return sum(1 for w in palabras if w[:4] in q_norm)

            if orden_fuentes:
                fuente_principal = max(
                    orden_fuentes,
                    key=lambda s: (_title_score(s), -orden_fuentes.index(s))
                )
            else:
                fuente_principal = docs[0].metadata.get('source') if docs else None

            score_elegido = _title_score(fuente_principal) if fuente_principal else 0
            n_palabras = len(q_norm.split())
            es_followup_o_vago = es_followup or (n_palabras <= 4 and score_elegido == 0)

            # CONTINUIDAD FUERTE: si ya hay un caso activo, NO cambiar de caso a menos
            # que el usuario nombre CLARAMENTE otro caso (coincidencia de título >= 2).
            # Así, las preguntas específicas/seguimiento se quedan en el caso actual.
            quedarse = bool(ultima_fuente) and (es_followup_o_vago or score_elegido < 2)

            if quedarse:
                if fuente_principal != ultima_fuente:
                    logger.info(f"↪️ Continuidad: mantengo el caso anterior ({ultima_fuente})")
                fuente_principal = ultima_fuente
            else:
                # Caso nuevo o primera consulta -> validar relevancia
                if not docs or (best_score is not None and best_score > 0.55):
                    self.estadisticas['queries_exitosas'] += 1
                    return {
                        'exito': True,
                        'respuesta': (
                            "No encontré un caso que coincida con tu consulta. "
                            "¿Puedes indicarme el proceso? Por ejemplo: radicar una solicitud, "
                            "reasignar un caso bloqueado, cerrar un caso, "
                            "corregir datos de una factura o validar pagos no aplicados."
                        ),
                        'sources': [],
                        'fuente': ultima_fuente,
                        'modo': 'RAG',
                        'timestamp': datetime.now().isoformat()
                    }

            logger.info(f"📄 Documento elegido: {fuente_principal}")

            # 4) Traer TODOS los fragmentos de ese documento (respuesta completa)
            chunks_doc = []
            try:
                data = self.vectorstore._collection.get(
                    where={"source": fuente_principal}
                )
                textos = data.get('documents') or []
                metas = data.get('metadatas') or []
                pares = list(zip(textos, metas))
                pares.sort(key=lambda x: (x[1] or {}).get('chunk_id', 0))
                chunks_doc = pares
            except Exception as e:
                logger.warning(f"⚠️ No se pudieron traer todos los chunks: {e}")

            if not chunks_doc:
                chunks_doc = [
                    (d.page_content, d.metadata)
                    for d in docs
                    if d.metadata.get('source') == fuente_principal
                ]

            # 5) Construir contexto completo (tope de seguridad de tokens)
            contexto_texto = "\n\n".join(t for t, _ in chunks_doc)
            if len(contexto_texto) > 12000:
                contexto_texto = contexto_texto[:12000]
            prompt_final = self.prompt_str.format(
                context=contexto_texto, question=pregunta
            )

            # 6) Generar respuesta
            respuesta_llm = self.llm.invoke([HumanMessage(content=prompt_final)])
            self.estadisticas['queries_exitosas'] += 1

            # FUENTE COMPLETA: reconstruimos TODO el documento en un solo bloque
            # (sin solapamientos ni cabeceras repetidas) para que se vea completo.
            meta_doc = (chunks_doc[0][1] if chunks_doc else {}) or {}
            titulo_doc = meta_doc.get('titulo') or meta_doc.get('source') or fuente_principal
            texto_completo_fuente = _unir_chunks(
                [t for t, _ in chunks_doc], titulo=titulo_doc
            )
            sources = [
                {
                    'contenido': texto_completo_fuente,
                    'metadata': meta_doc,
                    'archivo': meta_doc.get('source', fuente_principal or 'desconocido')
                }
            ]

            return {
                'exito': True,
                'respuesta': respuesta_llm.content,
                'sources': sources,
                'fuente': fuente_principal,
                'modo': 'RAG',
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Error en query: {e}", exc_info=True)
            self.estadisticas['queries_fallidas'] += 1

            return {
                'exito': False,
                'respuesta': f"❌ Error procesando pregunta: {str(e)}",
                'sources': [],
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


    def obtener_estado(self) -> Dict[str, Any]:
        """Obtener estado actual del motor"""
        return {
            'estado': self.estado,
            'chain_activa': self.chain is not None,
            'vectorstore_activo': self.vectorstore is not None,
            'memoria_activa': self.memory is not None,
            'estadisticas': self.estadisticas
        }

# Singleton global
_motor_global = None

def obtener_motor() -> ProcesosIAEngine:
    """Obtener instancia global del motor"""
    global _motor_global
    if _motor_global is None:
        _motor_global = ProcesosIAEngine()
    return _motor_global
