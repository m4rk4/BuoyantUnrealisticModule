from urllib.parse import parse_qs, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://mm-v2.simplestream.com/iframe/player.php?key=3Li3Nt2Qs8Ct3Xq9Fi5Uy0Mb2Bj0Qs&player=GB003&uvid=52338809&type=vod
    split_url = urlsplit(url)
    params = parse_qs(split_url.query)
    if not params.get('uvid') or not params.get('key'):
        logger.warning('unhandled url ' + url)
        return None

    api_url = 'https://v2-streams-elb.simplestreamcdn.com/streams/api/show/stream/{}?key={}&platform=chrome&autoplay=click&muted=0&mobileWeb=0&gdpr=0&gdpr_consent=null'.format(params['uvid'][0], params['key'][0])
    api_json = utils.post_url(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = params['uvid'][0]
    item['_image'] = 'https://thumbnails.simplestreamcdn.com/vista/ondemand/1080/{}.jpg'.format(item['id'])
    item['_video'] = api_json['response']['stream']
    item['content_html'] = utils.add_video(item['_video'], 'application/x-mpegURL', item['_image'], args.get('caption'))
    return item
