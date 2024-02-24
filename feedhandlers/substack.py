import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://substack.com/api/v1/posts/by-id/96541363
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = '{}://{}/api/v1/posts/{}'.format(split_url.scheme, split_url.netloc, paths[1])
    post_json = utils.get_url_json(api_url)
    if not post_json:
        return None
    return get_post(post_json, args, site_json, save_debug)


def get_post(post_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']

    item['url'] = post_json['canonical_url']
    split_url = urlsplit(item['url'])

    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['post_date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in post_json['publishedBylines']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json.get('postTags'):
        item['tags'] = []
        for it in post_json['postTags']:
            item['tags'].append(it['name'])

    if post_json.get('cover_image'):
        item['_image'] = post_json['cover_image']

    if post_json.get('description'):
        item['summary'] = post_json['description']

    item['content_html'] = ''
    if post_json['audience'] == 'only_paid':
        item['content_html'] += '<h2 style="text-align:center;"><a href="{}">This post is for paid subscribers</a></h2>'.format(item['url'])

    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subtitle'])

    if post_json.get('audio_items'):
        audio = next((it for it in post_json['audio_items'] if it['type'] == 'voiceover'), None)
        if not audio:
            audio = next((it for it in post_json['audio_items'] if it['type'] == 'tts'), None)
        item['_audio'] = audio['audio_url']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        #item['content_html'] += '<div><a href="{}"><img src="{}/static/play_button-48x48.png" style="float:left;" /><span>&nbsp;Listen to article</span></a></div><div style="clear:left;">&nbsp;</div>'.format(item['_audio'], config.server)
        item['content_html'] += '<div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen to article</a></span></div>'.format(item['_audio'], config.server)

    if post_json.get('podcastUpload'):
            item['_audio'] = post_json['podcast_url']
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            duration = []
            if post_json['podcast_duration'] >= 3600:
                duration.append('{:.0f} hr'.format(post_json['podcast_duration'] / 3600))
                duration.append('{:.0f} min'.format((post_json['podcast_duration'] % 3600) / 60))
            else:
                duration.append('{:.0f} min.'.format(post_json['podcast_duration'] / 60))
            poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(post_json['podcast_episode_image_url']))
            item['content_html'] += '<div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}"/></a><span>&nbsp;<a href="{0}">Listen now ({2})</a></span></div>'.format(item['_audio'], poster, ', '.join(duration))

    if post_json.get('body_html'):
        # utils.write_file(post_json['body_html'], './debug/debug.html')
        soup = BeautifulSoup(post_json['body_html'], 'html.parser')

        for el in soup.find_all(class_='subscription-widget-wrap'):
            el.decompose()

        for el in soup.find_all(class_=re.compile('button-wrap')):
            if el.name == None:
                continue
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                if re.search(r'comment|follow|learn more|schedule|share|subscribe|subscription', data_json['text'], flags=re.I) or re.search(r'subscribe', data_json['url']):
                    el.decompose()

        for el in soup.find_all('h5'):
            el.name = 'h2'

        for el in soup.find_all('blockquote'):
            if not el.get('class'):
                new_html = utils.add_blockquote(el.decode_contents())
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled blockquote in ' + item['url'])

        for el in soup.find_all(class_='pullquote'):
            # TODO: author/citation?
            new_html = utils.add_pullquote(el.get_text())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all(class_='captioned-image-container'):
            it = el.find('img')
            if not it:
                it = el.find('source')
            if it:
                if it.get('srcset'):
                    img_src = utils.image_from_srcset(it['srcset'], 1000)
                else:
                    img_src = it['src']
                it = el.find(class_='image-link')
                if it:
                    link = it['href']
                else:
                    link = ''
                it = el.find('figcaption')
                if it:
                    caption = it.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_image(img_src, caption, link=link)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled captioned-image-container in ' + item['url'])

        for el in soup.find_all(class_='youtube-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed('https://www.youtube-nocookie.com/embed/{}'.format(data_json['videoId']))
            else:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled youtube-wrap in ' + item['url'])

        for el in soup.find_all(class_='tweet'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed(data_json['url'])
            else:
                it = el.find(class_=['tweet-link-top', 'tweet-link-bottom'])
                if it:
                    new_html = utils.add_embed(it['href'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled tweet in ' + item['url'])

        for el in soup.find_all('iframe', class_='spotify-wrap'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all(class_='tiktok-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed(data_json['url'])
            else:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled tiktok-wrap in ' + item['url'])

        for el in soup.find_all(class_='embedded-post-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                split_data_url = urlsplit(data_json['url'])
                dt = datetime.fromisoformat(data_json['date'].replace('Z', '+00:00'))
                authors = []
                for it in data_json['bylines']:
                    authors.append(it['name'])
                new_html = '<div style="margin-left:5%; margin-right:5%; padding:8px; border:1px solid black; border-radius:10px;"><div><a href="{}://{}"><img src="{}" style="float:left; width:48px;"/><span style="font-size:1.1em; font-weight:bold;">{}</span></a></div><div style="clear:left;"></div><hr/>'.format(split_data_url.scheme, split_data_url.netloc, data_json['publication_logo_url'], data_json['publication_name'])
                new_html += '<div style="padding:8px;"><h4><a href="{}">{}</a></h4>{}</div><hr/>'.format(data_json['url'], data_json['title'], data_json['truncated_body_text'])
                new_html += '<div style="padding:8px;">{} &bull; {}</div></div>'.format(utils.format_display_date(dt, False), re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in soup.find_all(class_='embedded-publication-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = '<div style="margin-left:5%; margin-right:5%; padding:8px; border:1px solid black; border-radius:10px; text-align:center;"><a href="{}"><img src="{}" style="width:56px;"/><br/><span style="font-size:1.1em; font-weight:bold;">{}</span></a><br/>{}<br/><span style="font-size:0.9em;">By {}</span></div>'.format(data_json['base_url'], data_json['logo_url'], data_json['name'], data_json['hero_text'], data_json['author_name'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in soup.find_all(class_='poll-embed'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                poll_json = utils.get_url_json('{}://{}/api/v1/poll/{}'.format(split_url.scheme, split_url.netloc, data_json['id']))
                if poll_json:
                    new_html = '<div style="width:80%; margin-right:auto; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; padding:10px;"><h3>{}</h3>'.format(poll_json['question'])
                    for it in poll_json['options']:
                        pct = int(it['votes']/poll_json['total_votes']*100)
                        if pct >= 50:
                            new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}%</p></div>'.format(pct, 100-pct, it['label'], pct)
                        else:
                            new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}%</p></div>'.format(100-pct, pct, it['label'], pct)
                    new_html += '<div><small>{} votes &bull; '.format(poll_json['total_votes'])
                    dt = datetime.fromisoformat(poll_json['published_at'].replace('Z', '+00:00'))
                    delta = timedelta(hours=poll_json['expiry'])
                    if dt + delta < datetime.utcnow().replace(tzinfo=timezone.utc):
                        new_html += 'Poll closed'
                    else:
                        new_html += 'Poll open until ' + utils.format_display_date(dt + delta)
                    new_html += '</small></div></div>'
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled poll-embed in ' + item['url'])

        for el in soup.find_all(class_='cashtag-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                price_json = utils.get_url_json('{}://{}/api/v1/price/{}'.format(split_url.scheme, split_url.netloc, data_json['symbol']))
                #utils.write_file(price_json, './debug/price.json')
                if price_json:
                    if price_json.get('change_pct'):
                        if price_json['change_pct'] < 0:
                            change = '{:.2f}'.format(price_json['change_pct'])
                            color = 'red'
                            arrow = ' &#8595;'
                        elif price_json['change_pct'] > 0:
                            change = '{:.2f}'.format(price_json['change_pct'])
                            color = 'green'
                            arrow = ' &#8593;'
                        else:
                            change = '0.00'
                            color = 'orange'
                            arrow = ''
                    else:
                        change = '0.00'
                        color = 'orange'
                        arrow = ''
                    new_html = '<a href="https://substack.com/discover/stocks/{0}" style="color:{1};">{0} {2}{3}</a>'.format(data_json['symbol'][1:], color, change, arrow)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled cashtag-wrap in ' + item['url'])

        for el in soup.find_all('a', class_='footnote-anchor'):
            del el['class']
            el.wrap(soup.new_tag('sup'))

        for el in soup.find_all(class_='footnote'):
            it = el.find('a', class_='footnote-number')
            del it['class']
            new_html = '<table><tr><td style="vertical-align:top;">{}</td>'.format(str(it))
            it = el.find(class_='footnote-content')
            note = re.sub(r'^<p>(.*)</p>$', r'\1', it.decode_contents().replace('</p><p>', '<br/><br/>'))
            new_html += '<td style="vertical-align:top;">{}</td></tr></table>'.format(note)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all('span', class_='mention-wrap'):
            data_json = json.loads(el['data-attrs'])
            new_html = '<a href="https://open.substack.com/users/{}-{}?utm_source=mentions">{}</a>'.format(data_json['id'], data_json['name'].replace(' ', '-'), data_json['name'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all(class_=True):
            logger.warning('unhandled class {} in {}'.format(el['class'], item['url']))

        item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return item


def get_feed(url, args, site_json, save_debug=False):
    #return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    api_url = '{}://{}/api/v1/posts?limit=10&offset=0'.format(split_url.scheme, split_url.netloc)
    posts_json = utils.get_url_json(api_url)
    if not posts_json:
        return None
    if save_debug:
        utils.write_file(posts_json, './debug/feed.json')
    n = 0
    items = []
    feed = utils.init_jsonfeed(args)
    for post in posts_json:
        if save_debug:
            logger.debug('getting content from ' + post['canonical_url'])
        item = get_post(post, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = items.copy()
    return feed