import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus, unquote_plus

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def fix_links(el):
    for it in el.find_all('a'):
        if it.get('href'):
            if it['href'].startswith('/'):
                it['href'] = 'https://www.facebook.com'
            it['href'] = utils.get_redirect_url(it['href'])
    return


def format_content(item, media_html):
    if item['author'].get('image'):
        avatar = '{}/image?url={}&mask=circle'.format(config.server, quote_plus(item['author']['image']))
    else:
        avatar = '{}/image?width=40&height=40&mask=circle'.format(config.server)

    if item['author'].get('verified'):
        verified = '&nbsp;<small>&#9989;</small>'
    else:
        verified = ''

    if item.get('_timestamp'):
        dt = datetime.fromtimestamp(item['_timestamp']).replace(tzinfo=timezone.utc)
        display_date = '<br/><small>{}</small>'.format(utils.format_display_date(dt, False))
    else:
        display_date = ''

    item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{}"/><div style="overflow:hidden;"><a href="{}"><b>{}</b></a>{}{}</div></div><div style="clear:left;"></div>'.format(avatar, item['author']['url'], item['author']['name'], verified, display_date)

    if item.get('summary'):
        item['content_html'] += media_html

    if media_html:
        item['content_html'] += media_html

    item['content_html'] += '<a href="{}"><small>Open in Facebook</small></a></div>'.format(item['url'])
    return


def get_html_content(url, args, save_debug, post_html=''):
    if not post_html:
        post_url = re.sub('^https://(www\.)?facebook\.com', 'https://m.facebook.com', url)
        post_html = utils.get_url_html(post_url, user_agent='mobile')
        if not post_html:
            return None
        if save_debug:
            utils.write_file(post_html, './debug/debug.html')

    soup = BeautifulSoup(post_html, 'html.parser')

    item = {}

    el = soup.find('link', hreflang="x-default")
    if el:
        item['url'] = el['href']
    else:
        el = soup.find('meta', attrs={"property": "og:url"})
        if el:
            item['url'] = el['content']
        else:
            item['url'] = url

    split_url = urlsplit(item['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) > 1:
        item['id'] = paths[-1]
    else:
        if split_url.query:
            m = re.search(r'story_fbid=(\d+)', split_url.query)
            if m:
                item['id'] = m.group(1)
    if not item.get('id'):
        logger.warning('unable to determine id in ' + url)

    el = soup.find('code')
    content = BeautifulSoup(el.string, 'html.parser')
    if save_debug:
        utils.write_file(str(content), './debug/content.html')

    el = content.find('h1')
    if el:
        item['title'] = el.get_text()
    else:
        item['title'] = soup.title.get_text()
    if len(item['title']) > 50:
        item['title'] = item['title'][:50] + '...'

    el = content.find('abbr')
    if el:
        if el.get('data-sigil') and el['data-sigil'] == 'timestamp':
            data = json.loads(el['data-store'])
            dt_utc = datetime.fromtimestamp(data['time']).replace(tzinfo=timezone.utc)
        else:
            try:
                dt = datetime.strptime(el.string, '%B %d, %Y at %I:%M %p')
                tz_est = pytz.timezone('US/Eastern')
                dt_utc = tz_est.localize(dt).astimezone(pytz.utc)
            except:
                logger.warning('unable to determine post date/time in ' + url)
        if dt_utc:
            item['date_published'] = dt_utc.isoformat()
            item['_timestamp'] = dt_utc.timestamp()
            item['_display_date'] = utils.format_display_date(dt_utc)

    item['author'] = {}
    el = content.find('strong', class_='actor')
    if el:
        item['author']['name'] = el.get_text()
        el = content.find('a', class_='actor-link')
        if el:
            item['author']['url'] = 'https://www.facebook.com' + el['href']
    else:
        el = content.find('strong')
        if el:
            item['author']['name'] = el.get_text()
            if el.a:
                item['author']['url'] = 'https://www.facebook.com' + el.a['href']
        else:
            if len(paths) > 1:
                item['author']['name'] = paths[0]
                item['author']['url'] = 'https://www.facebook.com/' + paths[0]
    if not item.get('author'):
        logger.warning('unable to determine post author in ' + url)
        del item['author']

    el = content.find(class_='profpic')
    if el:
        if el.get('src'):
            item['author']['image'] = el['src'].replace('&amp;', '&')
        elif el.get('style'):
            m = re.search('url\(\'([^\']+)\'\)', el['style'])
            if m:
                def sub_entities(matchobj):
                    return unquote_plus('%{}'.format(matchobj.group(1)))
                item['author']['image'] = re.sub(r'\\\\([0-9a-f]{2})\s', sub_entities, m.group(1))

    el = content.find(attrs={"aria-label": "Verified Page"})
    if el:
        item['author']['verified'] = True

    media_html = ''

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']

    el = soup.find('meta', attrs={"property": "og:video"})
    if el:
        item['_video'] = el['content']

    el = soup.find('meta', attrs={"name": "description"})
    if el:
        item['summary'] = el['content']

    el = soup.find('meta', attrs={"property": "og:type"})
    if el:
        if el['content'] == 'video.other':
            media_html += utils.add_video(item['_video'], 'video/mp4', item['_image'], width='480px')

    item['summary'] = ''
    elems = content.find_all('p')
    if elems:
        for el in elems:
            fix_links(el)
            item['summary'] += str(el)
    else:
        el = content.find('div', class_='')
        if el:
            el.name = 'p'
            fix_links(el)
            item['summary'] += str(el)

    if item.get('_image'):
        media_html += utils.add_image(item['_image'], width='480px')

    format_content(item, media_html)
    return item


def get_story_content(url, args, save_debug):
    post_url = re.sub('^https://(www\.)?facebook\.com', 'https://m.facebook.com', url)
    post_html = utils.get_url_html(post_url, user_agent='mobile')
    if not post_html:
        return None
    if save_debug:
        utils.write_file(post_html, './debug/debug.html')

    soup = BeautifulSoup(post_html, 'html.parser')
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if not el:
        logger.warning('uable to find ld+json data in ' + url)
        return get_html_content(url, args, save_debug, post_html)

    ld_json = json.loads(el.string)
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    story_body = soup.find(class_='story_body_container')
    if save_debug:
        utils.write_file(str(story_body), './debug/content.html')

    item = {}
    item['id'] = ld_json['identifier']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    date = re.sub(r'([+|-])(\d\d)(\d\d)$', r'\1\2:\3', ld_json['dateCreated'])
    dt = datetime.fromisoformat(date).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    display_date = utils.format_display_date(dt, False)
    date = re.sub(r'([+|-])(\d\d)(\d\d)$', r'\1\2:\3', ld_json['dateModified'])
    dt = datetime.fromisoformat(date).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if ld_json.get('author'):
        item['author']['name'] = ld_json['author']['name']
        author_url = ld_json['url']
    else:
        el = story_body.find('strong')
        if el:
            item['author']['name'] = el.get_text()
            author_url = el.a['href']

    avatar = '{}/image?width=40&height=40&mask=circle'.format(config.server)
    el = story_body.find('img', class_='profpic')
    if el:
        avatar = '{}/image?url={}&height=40&mask=circle'.format(config.server, quote_plus(el['src']))

    el = story_body.find(attrs={"aria-label": "Verified Page"})
    if el:
        verified = '&#9989;'
    else:
        verified = ''

    item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{}"/><div style="overflow:hidden;"><a href="{}"><b>{}</b></a><small>{}</small><br/><small>{}</small></div></div><div style="clear:left;"></div>'.format(avatar, author_url, item['author']['name'], verified, display_date)

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']

    item['summary'] = ld_json['articleBody']

    for el in story_body.find_all('p'):
        item['content_html'] += str(el)

    el = story_body.find('section', attrs={"data-store": True})
    if el:
        img_src = el.img['src'].replace('&amp;', '&')
        link = utils.get_redirect_url(el.a['href'])
        captions = []
        if el.h3:
            captions.append('<a href="{}">{}</a>'.format(link, el.h3.get_text()))
        if el.h4:
            captions.append(el.h4.get_text())
        item['content_html'] += utils.add_image(img_src, ' | '.join(captions), width='480px', link=link)

    item['content_html'] += '<a href="{}"><small>Open in Facebook</small></a></div>'.format(item['url'])
    return item



def get_content(url, args, save_debug=False):
    # Try loading via an embed url - maybe this prevents potential rate-limiting
    # https://developers.facebook.com/docs/plugins/embedded-posts
    clean_url = utils.clean_url(url)
    embed_url = 'https://www.facebook.com/plugins/post.php?href={}&_fb_noscript=1'.format(quote_plus(clean_url))
    embed_html = utils.get_url_html(embed_url)
    if not embed_html:
        logger.warning('unable to get embed html, trying get_html_content for ' + url)
        return get_html_content(url, args, save_debug)

    if save_debug:
        utils.write_file(embed_html, './debug/debug.html')

    if re.search(r'no longer available', embed_html):
        logger.warning('post no longer available, trying get_html_content for ' + url)
        item = get_html_content(url, args, save_debug)
        if not item:
            item = {}
            item['id'] = url
            item['url'] = url
            item['title'] = 'This Facebook post is no longer available'
            item['content_html'] = '<blockquote><b><a href="{}">This Facebook post</a> is no longer available. It may have been removed or the privacy settings of the post may have changed.</b></blockquote>'.format(url)
        return item

    soup = BeautifulSoup(embed_html, 'html.parser')

    post_json = None
    el = soup.find('script', string=re.compile(r'sdkurl'))
    if el:
        m = re.search(r's\.handle\((.*)\);requireLazy', el.string)
        if m:
            post_json = json.loads(m.group(1))
            if save_debug:
                utils.write_file(post_json, './debug/facebook.json')

    content = soup.find('div', role='feed')
    if not content and post_json:
        content = BeautifulSoup(post_json['markup'][0][1]['__html'], 'html.parser')
    else:
        content = soup

    item = {}

    el = soup.find('link', rel='canonical')
    if el:
        item['url'] = el['href']
    else:
        item['url'] = url

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) > 1:
        item['id'] = paths[-1]
    else:
        item['id'] = url

    el = content.find(attrs={"data-utime": True})
    if el:
        dt = datetime.fromtimestamp(int(el['data-utime'])).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    # The first link should be the author
    el = content.find('a')
    item['author'] = {}
    item['author']['name'] = el.img['aria-label']
    item['author']['url'] = 'https://www.facebook.com' + el['href']
    item['author']['image'] = el.img['src']
    el = content.find(attrs={"aria-label": "Verified Page"})
    if el:
        item['author']['verified'] = True

    el = content.find(class_='userContent')
    if el:
        item['summary'] = str(el)
        title = el.get_text()
        if len(title) > 50:
            item['title'] = title[:50] + '...'
        else:
            item['title'] = title
    if not item.get('title'):
        item['title'] = 'A Facebook post by ' + item['author']['name']

    media_html = ''

    if soup.find('video'):
        if post_json:
            for inst in post_json['instances']:
                if inst[2][0].get('videoData'):
                    item['_video'] = inst[2][0]['videoData'][0]['sd_src_no_ratelimit']
                    el = soup.find('img', src=re.compile(r'\.jpg'))
                    if el:
                        item['_image'] = el['src']
                        print(item['_image'])
                        media_html += utils.add_video(item['_video'], 'video/mp4', item['_image'], width=480)

    elements = soup.find_all('script', attrs={"type": "application/ld+json"})
    if elements:
        for el in elements:
            ld_json = json.loads(el.string)
            if ld_json.get('image'):
                if ld_json['image'].get('caption'):
                    caption = re.sub(r'@\[(\d+):(\d+):([^\]]+)\]', '<a href="\\1">\\3</a>', ld_json['image']['caption'])
                else:
                    caption = ''
                media_html += '<br/>' + utils.add_image('{}/image?url={}&width=480'.format(config.server, quote_plus(ld_json['image']['contentUrl'])), caption, width='480px', link=ld_json['image']['contentUrl'])
                if not item.get('_image'):
                    item['_image'] = ld_json['image']['contentUrl']
    else:
        for el in content.find_all('a'):
            if el.img and el.img['src'].startswith('https://scontent') and el.img['src'] != item['author']['image']:
                item['_image'] = el.img['src']
                media_html += '<br/>' + utils.add_image('{}/image?url={}&width=480'.format(config.server, quote_plus(item['_image'])), width='480px', link=item['_image'])

    format_content(item, media_html)
    return item