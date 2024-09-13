from utils import models
from utils.logger import get_logger

from events import logic as event_logic

from plugins.eschol import logic

logger = get_logger(__name__)

PLUGIN_NAME = 'ESCHOLARSHIP PUBLISHING PLUGIN'
DISPLAY_NAME = PLUGIN_NAME
DESCRIPTION = 'middleware between janeway and escholorship'
AUTHOR = 'California Digital Library'
VERSION = 0.1
SHORT_NAME = 'eschol'
MANAGER_URL = 'eschol_manager'

def install():
    ''' install this plugin '''
    plugin, created = models.Plugin.objects.get_or_create(
        name=SHORT_NAME,
        defaults={
            "enabled": True,
            "version": VERSION,
            "display_name": DISPLAY_NAME,
        }
    )

    if created:
        print(f'Plugin {PLUGIN_NAME} installed.')
    elif plugin.version != VERSION:
        print(f'Plugin updated: {VERSION} -> {plugin.version}')
        plugin.version = VERSION
        plugin.display_name = DISPLAY_NAME
        plugin.save()
    else:
        print(f'Plugin {PLUGIN_NAME} is already installed.')

def register_for_events():
    '''register for events '''
    pass

def hook_registry():
    ''' connect a hook with a method in this plugin's logic '''
    logger.debug('hook_registry called for eschol plugin')
    event_logic.Events.register_for_event(event_logic.Events.ON_ARTICLE_PUBLISHED,
                                          logic.article_to_eschol)
