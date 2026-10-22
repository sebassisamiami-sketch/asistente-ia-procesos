# chat_procesos.py - Procesador de Chat
"""
Gestor de procesamiento de mensajes de chat
Incluye enriquecimiento de prompts por rol, persistencia y ahorro de tokens
"""

import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from ia_motor import obtener_motor

logger = logging.getLogger(__name__)


def _normalizar_texto(s: str) -> str:
    """Normaliza texto para detectar saludos/cierres tolerando errores de
    escritura: minúsculas, sin tildes, sin signos, y colapsa letras repetidas
    (ej. 'graciaas', 'graciasss', 'holaa' -> 'gracias', 'gracias', 'hola')."""
    s = (s or "").lower().strip()
    # quitar tildes/acentos
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    # dejar solo letras, números y espacios
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    # colapsar letras repetidas (graciaas -> gracias)
    s = re.sub(r'(.)\1+', r'\1', s)
    # colapsar espacios
    s = re.sub(r'\s+', ' ', s).strip()
    return s

class ChatProcessor:
    """
    Procesa mensajes de chat con contexto de rol
    Gestiona historial local y persistencia
    """
    
    def __init__(self, usuario: str, rol: str):
        """Inicializar processor"""
        self.usuario = usuario
        self.rol = rol
        self.motor_ia = obtener_motor()
        self.historial_local = []
        self.ultima_fuente = None  # ultimo documento/caso usado (para seguimiento)
        self.archivo_sesion = f"data/sessions/{usuario}_{rol}.json"
        
        Path("data/sessions").mkdir(parents=True, exist_ok=True)
        logger.info(f"ChatProcessor iniciado para {usuario} ({rol})")
    
    def _cargar_memoria_usuario(self):
        """Cargar historial previo del usuario"""
        try:
            if Path(self.archivo_sesion).exists():
                with open(self.archivo_sesion, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.historial_local = data.get('historial', [])
                    logger.info(f"✅ Sesión anterior cargada ({len(self.historial_local)} mensajes)")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo cargar sesión anterior: {e}")
    
    def _enriquecer_prompt(self, mensaje: str) -> str:
        """Enriquecer prompt según rol"""
        prompts_rol = {
            "Administrador": f"""
            Eres un asistente administrativo corporativo de Andina Servicios.
            Usuario: {self.usuario} (Administrador)
            
            Tienes acceso completo a:
            - Manuales de solicitudes
            - Manuales de facturación
            - Políticas administrativas
            - Información de usuarios y accesos
            
            Proporciona respuestas detalladas y precisas.
            """,
            "Analista": f"""
            Eres un asistente analista de Andina Servicios.
            Usuario: {self.usuario} (Analista)
            
            Tienes acceso a:
            - Manuales de solicitudes
            - Manuales de facturación
            - Reportes analíticos
            
            Proporciona análisis precisos y detallados.
            """
        }
        
        # Enviamos la pregunta LIMPIA al motor para que la búsqueda en los
        # documentos sea precisa. El rol y el tono se controlan en el prompt
        # del motor (ia_motor.py), no aquí.
        _ = prompts_rol  # se mantiene por compatibilidad
        return mensaje
    
    def procesar_mensaje(self, mensaje: str, contexto: Dict = None) -> Dict[str, Any]:
        """Procesar mensaje del usuario y gestionar salidas tempranas"""
        try:
            # Validaciones de integridad
            if not mensaje or len(mensaje.strip()) < 1:
                return {
                    'exitoso': False,
                    'mensaje': mensaje,
                    'respuesta': "❌ Mensaje vacío",
                    'timestamp': datetime.now().isoformat(),
                    'usuario': self.usuario,
                    'rol': self.rol
                }
            
            if len(mensaje) > 5000:
                return {
                    'exitoso': False,
                    'mensaje': mensaje[:100] + "...",
                    'respuesta': "❌ Mensaje muy largo (máximo 5000 caracteres)",
                    'timestamp': datetime.now().isoformat(),
                    'usuario': self.usuario,
                    'rol': self.rol
                }

            # 🚨 FILTRO INTELIGENTE DE CIERRE DE CASOS (AHORRO DE TOKENS) 🚨
            clean_msg = _normalizar_texto(mensaje)
            frases_cierre = [
                "gracias", "muchas gracias", "mil gracias", "ok gracias",
                "gracias crack", "caso cerrado", "ya quedo", "listo", "fin",
                "perfecto gracias", "vale gracias", "thanks", "thank you"
            ]

            if any(
                f == clean_msg
                or clean_msg.startswith(f + " ")
                or clean_msg.endswith(" " + f)
                or (f in clean_msg and len(clean_msg) <= len(f) + 12)
                for f in frases_cierre
            ):
                logger.info("🛑 Comando de cierre detectado. Abortando consumo de IA OpenAI.")
                # Al cerrar un caso, olvidamos el caso activo para que el siguiente
                # mensaje empiece de cero (evita arrastrar el caso anterior).
                self.ultima_fuente = None
                respuesta_cierre = {
                    'exitoso': True,
                    'mensaje_original': mensaje,
                    'respuesta': "🤖 **SISTEMA:** Caso cerrado formalmente. Memoria de contexto asegurada en tu historial local. Estoy listo para procesar un nuevo ticket, ¿en qué te puedo ayudar?",
                    'sources': [],
                    'timestamp': datetime.now().isoformat(),
                    'usuario': self.usuario,
                    'rol': self.rol,
                    'modo': 'SISTEMA_LOCAL'
                }
                self.historial_local.append(respuesta_cierre)
                self._guardar_sesion()
                return respuesta_cierre
            
            # 👋 FILTRO DE SALUDOS / CHARLA (no consume RAG)
            frases_saludo = [
                "hola", "buenas", "buenos dias", "buenas tardes",
                "buenas noches", "hey", "que tal", "como estas",
                "como vas", "saludos", "buen dia", "ola"
            ]
            if (any(clean_msg == f or clean_msg.startswith(f + " ") for f in frases_saludo)
                    and len(clean_msg) <= 30):
                respuesta_saludo = {
                    'exitoso': True,
                    'mensaje_original': mensaje,
                    'respuesta': (
                        "👋 ¡Hola! Soy el asistente de procesos de Andina Servicios. "
                        "Puedo ayudarte con casos como **radicar una solicitud**, "
                        "**reasignar un caso bloqueado**, **cerrar un caso**, "
                        "**corregir datos de una factura** "
                        "y **validar pagos no aplicados**.\n\n"
                        "¿Sobre cuál necesitas ayuda?"
                    ),
                    'sources': [],
                    'timestamp': datetime.now().isoformat(),
                    'usuario': self.usuario,
                    'rol': self.rol,
                    'modo': 'SISTEMA_LOCAL'
                }
                self.historial_local.append(respuesta_saludo)
                self._guardar_sesion()
                return respuesta_saludo

            logger.info(f"📨 Procesando mensaje de {self.usuario}: {mensaje[:50]}...")
            
            # Enriquecer prompt
            prompt_enriquecido = self._enriquecer_prompt(mensaje)
            
            # Obtener respuesta del motor (pasando el último caso para seguimiento)
            ctx = dict(contexto or {})
            ctx['rol'] = self.rol
            ctx['ultima_fuente'] = self.ultima_fuente
            resultado_motor = self.motor_ia.query(
                pregunta=prompt_enriquecido,
                contexto=ctx
            )

            # Recordar el caso actual para preguntas de seguimiento
            if resultado_motor.get('fuente'):
                self.ultima_fuente = resultado_motor.get('fuente')
            
            # Construir respuesta
            respuesta = {
                'exitoso': resultado_motor.get('exito', False),
                'mensaje_original': mensaje,
                'respuesta': resultado_motor.get('respuesta', ''),
                'sources': resultado_motor.get('sources', []),
                'timestamp': datetime.now().isoformat(),
                'usuario': self.usuario,
                'rol': self.rol,
                'modo': resultado_motor.get('modo', 'desconocido')
            }
            
            if not respuesta['exitoso']:
                respuesta['error'] = {
                    'mensaje': resultado_motor.get('error', 'Error desconocido'),
                    'detalles': resultado_motor.get('respuesta', '')
                }
            
            # Guardar en historial local
            self.historial_local.append(respuesta)
            
            # Persistir sesión
            self._guardar_sesion()
            
            logger.info(f"✅ Mensaje procesado exitosamente")
            return respuesta
        
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje: {e}", exc_info=True)
            return {
                'exitoso': False,
                'mensaje': mensaje,
                'respuesta': f"❌ Error: {str(e)}",
                'timestamp': datetime.now().isoformat(),
                'usuario': self.usuario,
                'rol': self.rol,
                'error': {
                    'mensaje': 'Error interno',
                    'detalles': str(e)
                }
            }
    
    def _guardar_sesion(self):
        """Guardar sesión en JSON"""
        try:
            data = {
                'usuario': self.usuario,
                'rol': self.rol,
                'historial': self.historial_local,
                'ultima_actualizacion': datetime.now().isoformat()
            }
            
            with open(self.archivo_sesion, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"✅ Sesión guardada")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo guardar sesión: {e}")
    
    def obtener_historial(self, ultimos: int = 50) -> List[Dict]:
        """Obtener últimos mensajes del historial"""
        return self.historial_local[-ultimos:] if self.historial_local else []
    
    def limpiar_historial(self) -> bool:
        """Limpiar historial de la sesión"""
        try:
            self.historial_local = []
            # Olvidamos también el caso activo: al limpiar el chat, el siguiente
            # mensaje NO debe arrastrar el caso anterior (evita confundir el caso).
            self.ultima_fuente = None
            self._guardar_sesion()
            logger.info(f"✅ Historial limpiado para {self.usuario}")
            return True
        except Exception as e:
            logger.error(f"❌ Error limpiando historial: {e}")
            return False
    
    def exportar_historial(self, formato: str = 'json') -> str:
        """Exportar historial a texto o json"""
        try:
            if formato == 'json':
                return json.dumps(self.historial_local, ensure_ascii=False, indent=2)
            
            elif formato == 'txt':
                lineas = [f"Historial de chat - {self.usuario} ({self.rol})"]
                lineas.append("=" * 60)
                
                for msg in self.historial_local:
                    lineas.append(f"\n👤 Usuario: {msg['mensaje_original']}")
                    lineas.append(f"🤖 IA: {msg['respuesta']}")
                    lineas.append(f"⏱️  {msg['timestamp']}")
                    lineas.append("-" * 40)
                
                return "\n".join(lineas)
        
        except Exception as e:
            logger.error(f"❌ Error exportando historial: {e}")
            return ""
