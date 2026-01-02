import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    return '{}://{}{}?w={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def add_media(media_id):
    media_html = ''
    media_json = utils.get_url_json('https://assets.msn.com/breakingnews/v1/' + media_id)
    # media_json = utils.get_url_json('https://cdn.query.prod.cms.msn.com/' + media_id)
    if not media_json:
        return media_html

    if media_json['$type'] == 'image':
        captions = []
        if media_json.get('title'):
            captions.append(media_json['title'])
        if media_json.get('attribution'):
            captions.append(media_json['attribution'])
        media_html = utils.add_image(resize_image(media_json['href']), ' | '.join(captions))
    elif media_json['$type'] == 'slideshow':
        ss_url = config.server + '/gallery?url=' + quote_plus('https://www.msn.com/' + media_json['_locale'] + '/' + '/ss-' + media_json['_id'])
        caption = '<a href="{}" target="_blank">View slideshow</a>: {}'.format(ss_url, media_json['title'])
        img_src = 'https://img-s-msn-com.akamaized.net/tenant/amp/entityid/{}.img'.format(media_json['slides'][0]['image']['href'].split('/')[-1])
        media_html = utils.add_image(resize_image(img_src), caption, link=ss_url, overlay=config.gallery_button_overlay)
    elif media_json['$type'] == 'video':
        if 'www.youtube.com' in media_json['sourceHref']:
            media_html = utils.add_embed(media_json['sourceHref'])
        else:
            if media_json.get('thumbnail'):
                poster_json = utils.get_url_json('https://assets.msn.com/breakingnews/v1/' + media_json['thumbnail']['href'])
                # poster_json = utils.get_url_json('https://cdn.query.prod.cms.msn.com/' + media_json['thumbnail']['href'])
                if poster_json:
                    poster = resize_image(poster_json['href'])
                else:
                    poster = media_json['thumbnail']['sourceHref']
            else:
                poster = ''
            # format 1004 = m3u8
            video = next((it for it in media_json['videoFiles'] if it['format'] == '1004'), None)
            if not video:
                # format 1006 = m3u8
                video = next((it for it in media_json['videoFiles'] if it['format'] == '1006'), None)
                if not video:
                    # format 103 = mp4 (960x540)
                    video = next((it for it in media_json['videoFiles'] if it['format'] == '103'), None)
                    if not video:
                        # format 104 = mp4 (1280x720)
                        video = next((it for it in media_json['videoFiles'] if it['format'] == '104'), None)
            if video:
                video_src = video['href']
                if video.get('contentType'):
                    video_type = video['contentType']
                elif '.mp4' in video_src:
                    video_type = 'video/mp4'
                elif '.mpd' in video_src:
                    video_type = 'application/dash+xml'
                else:
                    video_type = 'application/x-mpegURL'
            else:
                video_src = media_json['sourceHref']
                if '.mp4' in video_src:
                    video_type = 'video/mp4'
                elif '.mpd' in video_src:
                    video_type = 'application/dash+xml'
                else:
                    video_type = 'application/x-mpegURL'
            media_html = utils.add_video(video_src, video_type, poster, media_json.get('caption'), use_videojs=True)
    return media_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    id = paths[-1].split('-')[-1]
    api_url = 'https://assets.msn.com/content/view/v2/Detail/{}/{}'.format(paths[0], id)
    article_json = utils.get_url_json(api_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    if article_json['jsonDataMap'].get('displayValue'):
        display_value = json.loads(article_json['jsonDataMap']['displayValue'])
    else:
        display_value = None

    item = {}
    item['id'] = article_json['id']

    if display_value:
        item['url'] = display_value['Url']
    else:
        #item['url'] = article_json['sourceHref']
        item['url'] = utils.clean_url(url)
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedDateTime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updatedDateTime'):
        dt = datetime.fromisoformat(article_json['updatedDateTime'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors += re.split(r'\sand\s|,\s', it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    if article_json.get('provider'):
        if item['author'].get('name'):
            item['author']['name'] += ' ({})'.format(article_json['provider']['name'])
        else:
            item['author']['name'] = article_json['provider']['name']

    item['tags'] = []
    if article_json.get('tags'):
        item['tags'] += [x['label'] for x in article_json['tags']]
    if article_json.get('satoriTags'):
        item['tags'] += [x['label'] for x in article_json['satoriTags'] if not x['label'].startswith('wf_')]
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].copy()
    if article_json.get('facets'):
        for it in article_json['facets']:
            if it['key'] == 'ProviderTags':
                item['tags'] += it['values'].copy()
    item['tags'] = list(set(item['tags']))
    if not item.get('tags'):
        del item['tags']

    if article_json.get('imageResources'):
        item['image'] = article_json['imageResources'][0]['url']
    elif article_json.get('thumbnail'):
        item['image'] = article_json['thumbnail']['image']['url']
    elif article_json.get('slides'):
        item['image'] = article_json['slides'][0]['image']['url']
    elif display_value and display_value.get('ImageUrl'):
        item['image'] = display_value['ImageUrl']

    if article_json.get('abstract'):
        item['summary'] = article_json['abstract']
    elif display_value and display_value.get('Snippet'):
        item['summary'] = display_value['Snippet']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)

    item['content_html'] = ''
    if article_json.get('videoMetadata'):
        if article_json.get('thirdPartyVideoPlayer'):
            item['content_html'] += utils.add_embed(article_json['seo']['canonicalUrl'])
        else:
            if article_json.get('thumbnail'):
                poster = resize_image(article_json['thumbnail']['image']['url'])
            elif 'image' in item:
                poster = item['image']
            else:
                poster = ''
            # format 1004 = m3u8
            video = next((it for it in article_json['videoMetadata']['externalVideoFiles'] if it['format'] == '1004'), None)
            if not video:
                # format 1006 = m3u8
                video = next((it for it in article_json['videoMetadata']['externalVideoFiles'] if it['format'] == '1006'), None)
                if not video:
                    # format 103 = mp4 (960x540)
                    video = next((it for it in article_json['videoMetadata']['externalVideoFiles'] if it['format'] == '103'), None)
                    if not video:
                        # format 104 = mp4 (1280x720)
                        video = next((it for it in article_json['videoMetadata']['externalVideoFiles'] if it['format'] == '104'), None)
                        if not video:
                            video = article_json['videoMetadata']['externalVideoFiles'][0]
            if video:
                video_src = video['url']
                if video.get('contentType'):
                    video_type = video['contentType']
                elif '.mp4' in video_src:
                    video_type = 'video/mp4'
                elif '.mpd' in video_src:
                    video_type = 'application/dash+xml'
                else:
                    video_type = 'application/x-mpegURL'
            item['content_html'] += utils.add_video(video_src, video_type, poster, item['title'])
        if article_json['type'] == 'video':
            if 'summary' in item:
                item['content_html'] += '<p>' + item['summary'] + '</p>'
            return item

    if article_json.get('body'):
        # item['content_html'] += article_json['body']
        def sub_img(matchobj):
            return add_media(matchobj.group(1))
        body_html = re.sub(r'<img[^>]*data-document-id="([^"]+)"[^>]*>', sub_img, article_json['body'])

        soup = BeautifulSoup(body_html, 'html.parser')
        if save_debug:
            utils.write_file(str(soup), './debug/debug.html')

        for el in soup.find_all(class_=re.compile(r'tabula')):
            el.decompose()

        for el in soup.find_all(class_='related-entries'):
            el.decompose()

        for el in soup.find_all(attrs={"data-id": "injected-recirculation-link"}):
            el.decompose()

        for el in soup.select('p:has(> a > strong)'):
            if el.string and el.string.isupper():
                el.decompose()

        for el in soup.find_all(class_='buy-block-info'):
            el.name = 'p'

        for el in soup.find_all(class_=['content-list-component', 'buy-block-promo']):
            el.unwrap()

        for el in soup.find_all(class_=['wp-block-heading', 'wp-block-list']):
            el.attrs = {}

        for el in soup.find_all('a', class_='buy-block-cta'):
            new_html = utils.add_button(el['href'], el.string)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        # This was removing some content. Replace by re.sub above.
        # for el in soup.find_all('img', attrs={"data-document-id": True}):
        #     new_html = add_media(el['data-document-id'])
        #     if new_html:
        #         new_el = BeautifulSoup(new_html, 'html.parser')
        #         el.replace_with(new_el)
        #     else:
        #         logger.warning('unhandled img in ' + url)

        for el in soup.find_all(attrs={"data-embed-type": True}):
            new_html = ''
            if el['data-embed-type'] == 'social-auto':
                embed = next((it for it in article_json['socialEmbeds'] if it['id'] == el['data-embed-id']), None)
                if embed:
                    new_html = utils.add_embed(embed['postUrl'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                if el.parent and el.parent.name == 'div':
                    el.parent.insert_after(new_el)
                    el.parent.decompose()
                else:
                    el.insert_after(new_el)
                    el.decompose()
            else:
                logger.warning('unhandled data-embed-type {} in {}'.format(el['data-embed-type'], url))

        item['content_html'] += str(soup)

    if article_json.get('slides'):
        item['_gallery'] = []
        item['content_html'] += '<h3><a href="{}/gallery?url={}" target="_blank">View as slideshow</a></h3>'.format(config.server, quote_plus(item['url']))
        for slide in article_json['slides']:
            img_src = slide['image']['url']
            thumb = resize_image(img_src, 640)
            if slide['image'].get('attribution'):
                caption = slide['image']['attribution']
            else:
                caption = ''
            desc = ''
            if slide.get('title'):
                desc += '<h4>{}</h4>'.format(slide['title'])
            if slide.get('body'):
                desc += slide['body']
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
            item['content_html'] += utils.add_image(resize_image(slide['image']['url']), caption, desc=desc)

    if article_json.get('sourceHref') and urlsplit(article_json['sourceHref']).netloc != 'www.msn.com':
        item['content_html'] += '<h2>Original article</h2>'
        item['content_html'] += utils.add_embed(article_json['sourceHref'])
    return item


def get_card_item(url, args, site_json, save_debug):
    if save_debug:
        logger.debug('getting content for ' + url)
    item = get_content(url, args, site_json, save_debug)
    if item:
        if utils.filter_item(item, args) == True:
            return item
    return None


def get_card_items(cards, args, site_json, save_debug):
    card_items = []
    for card in cards:
        if card.get('subCards'):
            return get_card_items(card['subCards'], args, site_json, save_debug)
        elif not card.get('type'):
            continue
        elif card['type'] == 'nativead' or card['type'] == 'infopane' or card['type'] == 'placeholder':
            continue
        elif card['type'] == 'article' or card['type'] == 'video' or card['type'] == 'slideshow':
            card_url = 'https://www.msn.com/' + card['locale'] + '/' + card['id']
            if save_debug:
                logger.debug('getting content for ' + card_url)
            item = get_content(card_url, args, site_json, save_debug)
            if item:
                card_items.append(item)
        else:
            logger.warning('unhandled card type ' + card['type'])
    return card_items


def get_section_items(sections, args, site_json, save_debug):
    section_items = []
    for section in sections:
        if section.get('cards'):
            section_items += get_card_items(section['cards'], args, site_json, save_debug)
        elif section.get('subSections'):
            section_items += get_section_items(section['subSections'], args, site_json, save_debug)
    return section_items


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = ''
    # TODO: homepage
    if 'source' in paths:
        id = re.sub(r'^sr-', '', paths[-1])
        api_url = 'https://assets.msn.com/service/news/feed/pages/providerfullpage?market={}&query=newest&CommunityProfileId={}&apikey=0QfOX3Vn51YCzitbLaRkTTBadtWpgTN8NZLW0C1SEM'.format(paths[0], id)
    elif 'topic' in paths:
        id = re.sub(r'^tp-', '', paths[-1])
        api_url = 'https://assets.msn.com/service/news/feed/pages/channelfeed?InterestIds={}&apikey=0QfOX3Vn51YCzitbLaRkTTBadtWpgTN8NZLW0C1SEM&cm={}'.format(id, paths[0])
    elif len(paths) == 1:
        api_url = 'https://assets.msn.com/service/news/feed/pages/weblayout?apikey=0QfOX3Vn51YCzitbLaRkTTBadtWpgTN8NZLW0C1SEM&audienceMode=adult&cm=' + paths[0]
    elif len(paths) == 0:
        api_url = 'https://assets.msn.com/service/news/feed/pages/weblayout?apikey=0QfOX3Vn51YCzitbLaRkTTBadtWpgTN8NZLW0C1SEM&audienceMode=adult&cm=en-us'
    if not api_url:
        logger.warning('unhandled feed url ' + url)
        return None

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    if save_debug:
        utils.write_file(api_json, './debug/feed.json')
    feed_items = get_section_items(api_json['sections'], args, site_json, save_debug)
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed