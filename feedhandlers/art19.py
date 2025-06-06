import uuid
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    #url = "https://rss.art19.com/episodes/38fdbbf7-bbda-4f11-8f88-0e66dd3a8550?content_only=true"
    headers = {
      "accept": "application/json",
      "accept-language": "en-US,en;q=0.9",
      "cache-control": "no-cache",
      "pragma": "no-cache",
      "sec-ch-ua": "\"Microsoft Edge\";v=\"117\", \"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"117\"",
      "sec-ch-ua-mobile": "?0",
      "sec-ch-ua-platform": "\"Windows\"",
      "sec-fetch-dest": "empty",
      "sec-fetch-mode": "cors",
      "sec-fetch-site": "same-site"
    }

    if 'episodes' in paths:
        ep_id = paths[paths.index('episodes') + 1]
        ep_json = utils.get_url_json('https://rss.art19.com/episodes/{}?content_only=true'.format(ep_id), headers=headers)
        if not ep_json:
            return None
        if save_debug:
            utils.write_file(ep_json, './debug/audio.json')

        item = {}
        item['id'] = ep_json['content']['episode_id']
        item['url'] = ep_json['content']['episode_share_url']
        item['title'] = ep_json['content']['episode_title']

        dt = datetime.fromisoformat(ep_json['performed_at'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, date_only=True)

        item['author'] = {
            "name": ep_json['content']['series_title']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        if ep_json['content']['artwork'].get('episode'):
            images = ep_json['content']['artwork']['episode']
        else:
            images = ep_json['content']['artwork']['show']

        img = utils.closest_dict(images, 'height', 640)
        item['image'] = img['url']

        item['_audio'] = ep_json['content']['media']['mp3']['url']
        attachment = {
            "url": item['_audio'],
            "mime_type": "audio/mpeg"
        }
        item['attachments'] = []
        item['attachments'].append(attachment)

        item['summary'] = ep_json['content']['episode_description']

        item['content_html'] = utils.add_audio(item['_audio'], item['image'], item['title'], item['url'], ep_json['content']['series_title'], ep_json['content']['series_show_page'], item['_display_date'], ep_json['content']['duration'])

        if not 'embed' in args and item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    elif 'shows' in paths:
        series_id = paths[paths.index('shows') + 1]
        try:
            uuid.UUID(series_id)
        except:
            series_id = ''
            if 'embed' not in paths:
                page_html = utils.get_url_html('{}://{}/{}/embed'.format(split_url.scheme, split_url.netloc, '/'.join(paths)))
            else:
                page_html = utils.get_url_html(url)
            if page_html:
                soup = BeautifulSoup(page_html, 'lxml')
                el = soup.find(attrs={"data-series-id": True})
                if el:
                    series_id = el['data-series-id']
        if not series_id:
            logger.warning('unable to determine series id in ' + url)
            return None
        show_json = utils.get_url_json('https://rss.art19.com/episodes?series_id={}&page%5Bnumber%5D=1&page%5Bsize%5D=10'.format(series_id))
        if not show_json:
            return None
        if save_debug:
            utils.write_file(show_json, './debug/show.json')

        ep_id = show_json['episodes'][0]['id']
        ep_json = utils.get_url_json('https://rss.art19.com/episodes/{}?content_only=true'.format(ep_id), headers=headers)
        if not ep_json:
            return None
        if save_debug:
            utils.write_file(ep_json, './debug/audio.json')

        item = {}
        item['id'] = ep_json['content']['series_id']
        item['url'] = ep_json['content']['series_show_page']
        item['title'] = ep_json['content']['series_title']

        dt = datetime.fromisoformat(ep_json['performed_at'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

        item['author'] = {
            "name": ep_json['content']['series_title']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        img = utils.closest_dict(ep_json['content']['artwork']['series'], 'height', 640)
        item['image'] = img['url']

        item['summary'] = ep_json['content']['series_description']

        item['content_html'] = utils.add_audio('', item['image'], item['title'], item['url'], '', '', '', '')
        item['content_html'] += '<h3 style="margin:8px;">Latest episodes:</h3>'
        item['content_html'] += utils.add_audio(ep_json['content']['media']['mp3']['url'], utils.closest_dict(ep_json['content']['artwork']['episode'], 'height', 640)['url'], ep_json['content']['episode_title'], ep_json['content']['episode_share_url'], '', '', utils.format_display_date(datetime.fromisoformat(ep_json['performed_at']), date_only=True), ep_json['content']['duration'], show_poster=False)

        if 'max' in args:
            n = min(int(args['max']), len(show_json['episodes']['items']))
        elif 'embed' in args:
            n = min(3, len(show_json['episodes']))
        else:
            n = min(10, len(show_json['episodes']))
        for i in range(1, n):
            ep_id = show_json['episodes'][i]['id']
            ep_json = utils.get_url_json('https://rss.art19.com/episodes/{}?content_only=true'.format(ep_id), headers=headers)
            if not ep_json:
                continue
            item['content_html'] += utils.add_audio(ep_json['content']['media']['mp3']['url'], utils.closest_dict(ep_json['content']['artwork']['episode'], 'height', 640)['url'], ep_json['content']['episode_title'], ep_json['content']['episode_share_url'], '', '', utils.format_display_date(datetime.fromisoformat(ep_json['performed_at']), date_only=True), ep_json['content']['duration'], show_poster=False)

    return item
