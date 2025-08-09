import aiohttp
import asyncio
from src.utils.responses import ResponseKey
from src.configs.settings import MAIN_BOT_TOKEN


# Configuration using ResponseKey Enum
MAIN_BOT_COMMANDS = ResponseKey.MAIN_BOT_COMMANDS
BOT_NAME = ResponseKey.BOT_NAME
BOT_SHORT_DESCRIPTION = ResponseKey.BOT_SHORT_DESCRIPTION
BOT_DESCRIPTION = ResponseKey.BOT_DESCRIPTION

async def call_api(session, method, params, lang_code=None):
    """Generic API caller with error handling"""
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/{method}"
    if lang_code:
        params['language_code'] = lang_code
    
    try:
        async with session.post(url, json=params) as response:
            data = await response.json()
            return {
                'success': data.get('ok', False),
                'description': data.get('description', 'Unknown error'),
                'method': method,
                'lang': lang_code
            }
    except Exception as e:
        return {
            'success': False,
            'description': str(e),
            'method': method,
            'lang': lang_code
        }

async def configure_bot():
    """Configure bot settings concurrently"""
    configs = [
        ('setMyName', 'name', BOT_NAME),
        ('setMyDescription', 'description', BOT_DESCRIPTION),
        ('setMyShortDescription', 'short_description', BOT_SHORT_DESCRIPTION),
        ('setMyCommands', 'commands', MAIN_BOT_COMMANDS)
    ]

    async with aiohttp.ClientSession() as session:
        tasks = []
        for method, param_key, response_key in configs:
            for lang in ['en', 'fa']:
                # Get the Response object from Enum member
                response_obj = response_key.value
                
                # Get language-specific value
                params = {param_key: getattr(response_obj, lang)}
                
                # Special handling for commands
                if method == 'setMyCommands':
                    params = {'commands': params[param_key]}
                
                tasks.append(call_api(session, method, params, lang))

        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result['success']:
                print(f"({result['lang'].upper()}) {result['method']} succeeded")
            else:
                print(f"({result['lang'].upper()}) {result['method']} failed: {result['description']}")

if __name__ == '__main__':
    asyncio.run(configure_bot())
