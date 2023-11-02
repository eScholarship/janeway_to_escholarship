from utils import models
from plugins.eschol import logic

from events import logic as event_logic

from utils.logger import get_logger

logger = get_logger(__name__)

PLUGIN_NAME = 'Janeway to Eschol Plugin'
DISPLAY_NAME = 'eschol'
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
        print('Plugin {0} installed.'.format(PLUGIN_NAME))
    elif plugin.version != VERSION:
        print('Plugin updated: {0} -> {1}'.format(VERSION, plugin.version))
        plugin.version = VERSION
        plugin.display_name = DISPLAY_NAME
        plugin.save()
    else:
        print('Plugin {0} is already installed.'.format(PLUGIN_NAME))

def register_for_events():
    '''register for events '''
    pass

def hook_registry():
    ''' connect a hook with a method in this plugin's logic '''
    logger.debug('hook_registry called for eschol plugin')
    event_logic.Events.register_for_event(event_logic.Events.ON_ARTICLE_PUBLISHED,
                                          logic.article_to_eschol)
