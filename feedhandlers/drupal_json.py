import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)

api_links = None

def get_api_json(api_path, data_type, id, filters=''):
    global api_links
    api_url = ''
    if api_links:
        if api_links.get(data_type):
            api_url = api_links[data_type]['href']
        else:
            dt = data_type.split('--')
            if api_links.get(dt[-1]):
                api_url = api_links[dt[-1]]['href']
    if not api_url:
        api_url = '{}{}'.format(api_path, data_type.replace('--', '/'))
    if id:
        api_url += '/{}'.format(id)
    if filters:
        api_url += '?{}'.format(filters)
    #headers = {"cache-control": "max-age=0"}
    api_json = utils.get_url_json(api_url)
    return api_json


def get_img_src(fig_html):
    if not fig_html:
        return '', ''
    figure = BeautifulSoup(fig_html, 'html.parser')
    img_src = figure.img['src']
    if figure.figcaption:
        caption = figure.figcaption.decode_contents()
    else:
        caption = ''
    return img_src, caption


def get_field_data(data, api_path, caption='', video_poster=''):
    if data['id'] == 'missing':
        return ''
    field_json = get_api_json(api_path, data['type'], data['id'])
    if field_json:
        #utils.write_file(field_json, './debug/field.json')
        if field_json['data']['type'] == 'media--image':
            captions = []
            if caption:
                captions.append(caption)
            if field_json['data']['attributes'].get('field_caption'):
                if isinstance(field_json['data']['attributes']['field_caption'], str):
                    captions.append(field_json['data']['attributes']['field_caption'])
                elif isinstance(field_json['data']['attributes']['field_caption'], dict):
                    captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', field_json['data']['attributes']['field_caption']['value'].strip()))
            if field_json['data']['attributes'].get('field_credit'):
                captions.append(field_json['data']['attributes']['field_credit'])
            if field_json['data']['attributes'].get('field_attribution'):
                captions.append(field_json['data']['attributes']['field_attribution'])
            if field_json['data']['attributes'].get('field_source'):
                if field_json['data']['attributes']['field_source'] not in captions:
                    captions.append(field_json['data']['attributes']['field_source'])
            if field_json['data']['attributes'].get('field_image_source'):
                if field_json['data']['attributes']['field_image_source'] not in captions:
                    captions.append(field_json['data']['attributes']['field_image_source'])
            if field_json['data']['relationships'].get('field_media_image'):
                img_src = get_field_data(field_json['data']['relationships']['field_media_image']['data'], api_path)
            elif field_json['data']['relationships'].get('image'):
                img_src = get_field_data(field_json['data']['relationships']['image']['data'], api_path)
            elif field_json['data']['relationships'].get('field_image'):
                img_src = get_field_data(field_json['data']['relationships']['field_image']['data'], api_path)
            else:
                logger.warning('unknown image source for {} {}'.format(field_json['data']['type'], field_json['data']['id']))
            return utils.add_image(img_src, ' | '.join(captions))

        elif field_json['data']['type'] == 'media--mpx_video':
            #utils.write_file(field_json, './debug/video.json')
            # Not sure if this changes
            player_url = 'https://vplayer.golfchannel.com/p/BxmELC/gc_player/select/media/{}'.format(field_json['data']['attributes']['field_media_pid'])
            player_html = utils.get_url_html(player_url)
            if player_html:
                #utils.write_file(player_html, './debug/video.html')
                player_soup = BeautifulSoup(player_html, 'html.parser')
                el = player_soup.find(id='player')
                if el:
                    video_src = utils.get_redirect_url(el['tp:releaseurl'])
                    if '.mp4' in video_src:
                        video_type = 'video/mp4'
                    else:
                        video_type = 'application/x-mpegURL'
                    if not video_poster:
                        if field_json['data']['relationships'].get('field_thumbnail') and field_json['data']['relationships']['field_thumbnail'].get('data'):
                            video_poster = get_field_data(field_json['data']['relationships']['field_thumbnail']['data'], api_path)
                        else:
                            el = player_soup.find('meta', attrs={"property": "og:image"})
                            if el:
                                video_poster = el['content']
                    caption = field_json['data']['attributes']['field_seo_headline']
                    return utils.add_video(video_src, video_type, video_poster, caption)

        elif field_json['data']['type'] == 'media--twitter':
            return utils.add_embed(field_json['data']['attributes']['field_media_twitter_1'])

        elif field_json['data']['type'] == 'media--instagram':
            return utils.add_embed(field_json['data']['attributes']['field_media_instagram'])

        elif field_json['data']['type'] == 'media--brightcove_video':
            return get_field_data(field_json['data']['relationships']['field_media_brightcove_video']['data'], api_path)

        elif field_json['data']['type'] == 'brightcove_video--brightcove_video':
            player = get_field_data(field_json['data']['relationships']['player']['data'], api_path)
            poster = get_field_data(field_json['data']['relationships']['poster']['data'], api_path)
            m = re.search(r'v1_static_(\d+)', poster)
            if m:
                return utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(m.group(1), player, field_json['data']['attributes']['video_id']))
            else:
                logger.warning('unhandled {} {}'.format(field_json['data']['type'], field_json['data']['id']))

        elif field_json['data']['type'] == 'brightcove_player--brightcove_player':
            return field_json['data']['attributes']['player_id']

        elif field_json['data']['type'] == 'file--file':
            if field_json['data']['attributes']['uri']['url'].startswith('/'):
                netloc = urlsplit(api_path).netloc
                file_url = 'https://{}{}'.format(netloc, field_json['data']['attributes']['uri']['url'])
            else:
                file_url = field_json['data']['attributes']['uri']['url']
            return file_url

        elif field_json['data']['type'] == 'paragraph--p_text':
            return field_json['data']['attributes']['field_p_text_text']['processed']

        elif field_json['data']['type'] == 'paragraph--p_media':
            media_html = ''
            for data in field_json['data']['relationships']['field_p_media_upload']['data']:
                media_html += get_field_data(data, api_path)
            return media_html

        elif field_json['data']['type'] == 'media--p_image':
            if field_json['data']['relationships']['field_p_media_img']['data']['meta'].get('title'):
                caption = field_json['data']['relationships']['field_p_media_img']['data']['meta']['title']
            else:
                caption = ''
            img_src = get_field_data(field_json['data']['relationships']['field_p_media_img']['data'], api_path)
            return utils.add_image(img_src, caption)

        else:
            logger.warning('unhandled {} {}'.format(field_json['data']['type'], field_json['data']['id']))
    return ''


def get_drupal_settings(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    drupal_settings = None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', attrs={"data-drupal-selector": "drupal-settings-json"})
    if el:
        drupal_settings = json.loads(el.string)
    return drupal_settings


def get_content(url, args, site_json, save_debug=False):
    drupal_settings = None
    page_type = ''
    node_id = ''
    uuid = ''

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if site_json.get('translate_path'):
        translate_url = '{}?path={}'.format(site_json['translate_path'], quote_plus(split_url.path))
        translate_json = utils.get_url_json(translate_url)
        if translate_json:
            uuid = translate_json['entity']['uuid']
            node_id = translate_json['entity']['id']
            page_type = '{}--{}'.format(translate_json['entity']['type'], translate_json['entity']['bundle'])
            #page_type = translate_json['jsonapi']['resourceName']
    else:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', attrs={"data-drupal-selector": "drupal-settings-json"})
        if el:
            drupal_settings = json.loads(el.string)
            if save_debug:
                utils.write_file(drupal_settings, './debug/drupal.json')
            try:
                uuid = drupal_settings['adobeLaunchData']['data']['metainfo']['uuid']
            except:
                node_id = drupal_settings['path']['currentPath'].split('/')[-1]

        if not uuid:
            el = soup.find('node-article-full', attrs={"uuid": True})
            if el:
                uuid = el['uuid']

        el = soup.find('body')
        if el and el.get('class'):
            m = re.search(r'node--?type-([^\s]+)', ' '.join(el['class']))
            if m:
                page_type = 'node--' + m.group(1)
            if not node_id:
                m = re.search(r'-node-(\d+)', ' '.join(el['class']))
                if m:
                    node_id = m.group(1)
        if not page_type and '/article/' in url:
            page_type = 'node--article'

    if site_json.get('default_page_type'):
        page_type = site_json['default_page_type']

    if not page_type:
        logger.warning('unknown page type for ' + url)
        return None

    global api_links
    if not api_links:
        api_json = utils.get_url_json(site_json['api_path'])
        if api_json:
            api_links = api_json['links']

    if uuid:
        api_json = get_api_json(site_json['api_path'], page_type, uuid, '')
    elif node_id:
        filters = 'filter[nid-filter][condition][path]=drupal_internal__nid&filter[nid-filter][condition][value]={}'.format(node_id)
        api_json = get_api_json(site_json['api_path'], page_type, '', filters)
    else:
        logger.warning('unknown uuid or node id for ' + url)
        return None
    if not api_json:
        return None

    if isinstance(api_json['data'], list):
        page_json = api_json['data'][0]
    else:
        page_json = api_json['data']
    if node_id and (\
            (page_json['attributes'].get('drupal_internal__nid') and page_json['attributes']['drupal_internal__nid'] != int(node_id)) or
            (page_json['attributes'].get('legacy_id') and page_json['attributes']['legacy_id'] != int(node_id))):
        logger.warning('jsonapi filter returned the wrong article for ' + url)
        return None
    return get_item(page_json, drupal_settings, url, args, site_json, save_debug)


def get_item(page_json, drupal_settings, url, args, site_json, save_debug):
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    item = {}
    item['id'] = page_json['id']

    if page_json['attributes'].get('metatag_normalized'):
        item['url'] = next((it['attributes']['href'] for it in page_json['attributes']['metatag_normalized'] if (it['tag'] == 'link' and it['attributes']['rel'] == 'canonical')), None)
    if not item.get('url'):
        if page_json['attributes'].get('path'):
            item['url'] = 'https://{}{}'.format(urlsplit(site_json['api_path']).netloc, page_json['attributes']['path']['alias'])
        elif page_json['attributes'].get('rel_alt_links'):
            m = re.search(r'/{}([^"]+)'.format(drupal_settings['path']['pathPrefix']), page_json['attributes']['rel_alt_links'][0])
            if m:
                item['url'] = 'https://{}{}'.format(urlsplit(site_json['api_path']).netloc, m.group(0))
    if not item.get('url'):
        item['url'] = url

    item['title'] = page_json['attributes']['title']

    if page_json['attributes'].get('created'):
        dt = datetime.fromisoformat(page_json['attributes']['created'])
    elif page_json['attributes'].get('published_on'):
        dt = datetime.fromisoformat(page_json['attributes']['published_on'])
    elif page_json['attributes'].get('publication_date'):
        dt = datetime.fromisoformat(page_json['attributes']['publication_date'])
    else:
        dt = None
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if page_json['attributes'].get('changed'):
        dt = datetime.fromisoformat(page_json['attributes']['changed'])
    elif page_json['attributes'].get('last_updated'):
        dt = datetime.fromisoformat(page_json['attributes']['last_updated'])
    else:
        dt = None
    if dt:
        item['date_modified'] = dt.isoformat()

    authors = []
    if page_json['relationships'].get('field_author') and page_json['relationships']['field_author'].get('data'):
        if isinstance(page_json['relationships']['field_author']['data'], list):
            for data in page_json['relationships']['field_author']['data']:
                api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
                if api_json:
                    authors.append(api_json['data']['attributes']['title'])
        else:
            data = page_json['relationships']['field_author']['data']
            api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
            if api_json:
                if api_json['data']['attributes'].get('title'):
                    authors.append(api_json['data']['attributes']['title'])
                elif api_json['data']['attributes'].get('name'):
                    authors.append(api_json['data']['attributes']['name'])
                else:
                    logger.warning('unknown field_author data attributes')
    elif page_json['relationships'].get('field_article_author') and page_json['relationships']['field_article_author'].get('data'):
        if isinstance(page_json['relationships']['field_article_author']['data'], list):
            for data in page_json['relationships']['field_article_author']['data']:
                api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
                if api_json:
                    authors.append(api_json['data']['attributes']['title'])
        else:
            data = page_json['relationships']['field_article_author']['data']
            api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
            if api_json:
                authors.append(api_json['data']['attributes']['title'])
    elif page_json['relationships'].get('field_authors') and page_json['relationships']['field_authors'].get('data'):
        for data in page_json['relationships']['field_authors']['data']:
            api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
            if api_json:
                authors.append(api_json['data']['attributes']['title'])
    elif page_json['relationships'].get('author_profile') and page_json['relationships']['author_profile'].get('data'):
        for data in page_json['relationships']['author_profile']['data']:
            api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
            if api_json:
                authors.append(api_json['data']['attributes']['title'])
    item['author'] = {}
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif site_json.get('default_author'):
        item['author']['name'] = site_json['default_author']
    else:
        item['author']['name'] = urlsplit(item['url']).netloc

    item['tags'] = []
    for key, val in page_json['relationships'].items():
        if val.get('data'):
            if isinstance(val['data'], list):
                for data in val['data']:
                    if data['type'].startswith('taxonomy_term'):
                        api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
                        if api_json:
                            if api_json['data']['attributes']['name'] not in item['tags']:
                                item['tags'].append(api_json['data']['attributes']['name'])
            else:
                data = val['data']
                if data['type'].startswith('taxonomy_term'):
                    api_json = get_api_json(site_json['api_path'], data['type'], data['id'])
                    if api_json:
                        if api_json['data']['attributes']['name'] not in item['tags']:
                            item['tags'].append(api_json['data']['attributes']['name'])
    if not item.get('tags'):
        del item['tags']

    lede_html = ''
    if page_json['attributes'].get('field_caption'):
        caption = page_json['attributes']['field_caption']
    else:
        caption = ''
    if page_json['relationships'].get('field_lede_image') and page_json['relationships']['field_lede_image'].get('data'):
        data_html = get_field_data(page_json['relationships']['field_lede_image']['data'], site_json['api_path'], caption=caption)
        item['_image'], caption = get_img_src(data_html)
        lede_html = data_html
    elif page_json['relationships'].get('field_article_hero_image') and page_json['relationships']['field_article_hero_image'].get('data'):
        data_html = get_field_data(page_json['relationships']['field_article_hero_image']['data'], site_json['api_path'], caption=caption)
        item['_image'], caption = get_img_src(data_html)
        lede_html = data_html
    elif page_json['relationships'].get('field_image_source') and page_json['relationships']['field_image_source'].get('data'):
        data_html = get_field_data(page_json['relationships']['field_image_source']['data'], site_json['api_path'], caption=caption)
        item['_image'], caption = get_img_src(data_html)
        lede_html = data_html
    elif page_json['relationships'].get('field_media') and page_json['relationships']['field_media'].get('data') and page_json['relationships']['field_media']['data']['type'] == 'media--image':
        data_html = get_field_data(page_json['relationships']['field_media']['data'], site_json['api_path'], caption=caption)
        item['_image'], caption = get_img_src(data_html)
        lede_html = data_html
    elif page_json['relationships'].get('field_image') and page_json['relationships']['field_image'].get('data'):
        if isinstance(page_json['relationships']['field_image']['data'], list):
            data = page_json['relationships']['field_image']['data'][0]
        else:
            data = page_json['relationships']['field_image']['data']
        data_html = get_field_data(data, site_json['api_path'], caption=caption)
        if data['type'] == 'file--file':
            item['_image'] = data_html
            data_html = utils.add_image(data_html, caption)
        else:
            item['_image'], caption = get_img_src(data_html)
        lede_html = data_html
    elif page_json['relationships'].get('field_thumbnail') and page_json['relationships']['field_thumbnail'].get('data'):
        data_html = get_field_data(page_json['relationships']['field_thumbnail']['data'], site_json['api_path'], caption=caption)
        item['_image'], caption = get_img_src(data_html)
    elif page_json['relationships'].get('teaser_image') and page_json['relationships']['teaser_image'].get('data'):
        data_html = get_field_data(page_json['relationships']['teaser_image']['data'], site_json['api_path'], caption=caption)
        item['_image'], caption = get_img_src(data_html)

    if page_json['attributes'].get('field_video_pid'):
        # Note: this may be specific to nbcsportsedge.com
        video_src = ''
        video_type = ''
        poster = ''
        caption = ''
        if not drupal_settings:
            drupal_settings = get_drupal_settings(item['url'])
        if drupal_settings and drupal_settings.get('svod'):
            svod_html = utils.get_url_html(drupal_settings['svod']['iframe_url'])
            if svod_html:
                svod_soup = BeautifulSoup(svod_html, 'html.parser')
                el = svod_soup.find('link', attrs={"type": "application/smil+xml"})
                if el:
                    video_src = utils.get_redirect_url(el['href'])
                    if '.mp4' in video_src:
                        video_type = 'video/mp4'
                    else:
                        video_type = 'application/x-mpegURL'
                el = svod_soup.find('meta', attrs={"property": "og:image"})
                if el:
                    poster = el['content']
                el = svod_soup.find('meta', attrs={"property": "og:description"})
                if el:
                    caption = el['content']
        if video_src:
            lede_html = utils.add_video(video_src, video_type, poster, caption)

    item['content_html'] = ''
    if page_json['type'] == 'node--gallery':
        item['content_html'] += '<p>{}</p>'.format(page_json['attributes']['body']['processed'])
        for it in page_json['relationships']['field_gallery_items']['data']:
            item['content_html'] += get_field_data(it, site_json['api_path'])

    elif page_json['type'] == 'node--video_page':
        if page_json['relationships'].get('field_mpx_video') and page_json['relationships']['field_mpx_video'].get('data'):
            item['content_html'] += get_field_data(page_json['relationships']['field_mpx_video']['data'], site_json['api_path'])
            item['content_html'] += '<p>{}</p>'.format(page_json['attributes']['body']['processed'])

    elif page_json['type'] == 'node--cars_car':
        # https://www.topgear.com/car-reviews/hyundai/ioniq-5
        if page_json['attributes'].get('field_cars_editor_title'):
            item['title'] = page_json['attributes']['field_cars_editor_title']
        item['content_html'] += '<h2><u>OVERVIEW</u></h2>'
        if page_json['attributes'].get('field_cars_what_is_it'):
            item['content_html'] += '<h2>What is it?</h2>' + page_json['attributes']['field_cars_what_is_it']['processed']
        if page_json['attributes'].get('field_cars_verdict'):
            item['content_html'] += '<h2>What\'s the verdict?</h2>'
            if page_json['attributes'].get('field_cars_verdict_text'):
                item['content_html'] += utils.add_pullquote(page_json['attributes']['field_cars_verdict_text'])
            item['content_html'] += page_json['attributes']['field_cars_verdict']['processed']
        item['content_html'] += '<hr/><h2><u>DRIVING</u></h2>'
        if page_json['attributes'].get('field_cars_driving'):
            item['content_html'] += '<h2>What is it like to drive?</h2>' + page_json['attributes']['field_cars_driving']['processed']
        item['content_html'] += '<hr/><h2><u>INTERIOR</u></h2>'
        if page_json['attributes'].get('field_cars_inside'):
            item['content_html'] += '<h2>What is it like to drive?</h2>' + page_json['attributes']['field_cars_inside']['processed']
        item['content_html'] += '<hr/><h2><u>BUYING</u></h2>'
        if page_json['attributes'].get('field_cars_owning'):
            item['content_html'] += '<h2>What is it like to drive?</h2>' + page_json['attributes']['field_cars_owning']['processed']
        item['content_html'] += '<hr/><h2><u>SPECS</u></h2><p><a href="{}/specs">View current specs and prices.</a></p>'.format(item['url'])
        lede_html = ''
        if page_json['relationships'].get('field_carousel_media') and page_json['relationships']['field_carousel_media'].get('data'):
            item['content_html'] += '<hr/><h2><u>GALLERY</u></h2>'
            for i, data in enumerate(page_json['relationships']['field_carousel_media']['data']):
                if i == 0:
                    if data['type'] != 'media--image':
                        lede_html = get_field_data(data, site_json['api_path'])
                    else:
                        item['content_html'] += get_field_data(data, site_json['api_path'])
                else:
                    item['content_html'] += get_field_data(data, site_json['api_path'])
        if not lede_html:
            data = get_field_data(page_json['relationships']['field_image']['data'], site_json['api_path'])
            if data.startswith('http'):
                lede_html += utils.add_image(data)
            else:
                lede_html += data
        if page_json['attributes'].get('field_cars_stand_first'):
            lede_html = '<p><em>{}</em></p>'.format(page_json['attributes']['field_cars_stand_first']) + lede_html
        lede_html += '<div>&nbsp;</div><div style="text-align:center; font-size:1.5em; font-weight:bold;">{}</div><div style="text-align:center;"><span style="font-size:2em; font-weight:bold;">{}</span>&nbsp;/10</div>'.format(page_json['attributes']['title'], page_json['attributes']['field_cars_rating'])
        if page_json['attributes'].get('field_cars_what_we_say'):
            lede_html += '<p><b>{}</b></p>'.format(page_json['attributes']['field_cars_what_we_say'])
        if page_json['attributes'].get('field_cars_verdict_for'):
            lede_html += '<p><b>GOOD STUFF:</b><br/>{}</p>'.format(page_json['attributes']['field_cars_verdict_for'])
        if page_json['attributes'].get('field_cars_verdict_against'):
            lede_html += '<p><b>BAD STUFF:</b><br/>{}</p>'.format(page_json['attributes']['field_cars_verdict_against'])
        if page_json['attributes'].get('tg_price_range_field'):
            lede_html += '<p><b>PRICE:</b><br/>£{:,.0f} &ndash; £{:,.0f}</p>'.format(float(page_json['attributes']['tg_price_range_field']['min_price_range']), float(page_json['attributes']['tg_price_range_field']['max_price_range']))
        item['content_html'] = lede_html + '<hr/>' + item['content_html']

    elif page_json['type'] == 'node--article' or page_json['type'] == 'node--news_article' or page_json['type'] == 'node--cars_road_test':
        if page_json['attributes'].get('field_introduction'):
            item['content_html'] += '<p><em>{}</em></p>'.format(page_json['attributes']['field_introduction'])

        if page_json['relationships'].get('field_mpx_video_lede') and page_json['relationships']['field_mpx_video_lede'].get('data'):
            if lede_html:
                poster, caption = get_img_src(lede_html)
            lede_html = get_field_data(page_json['relationships']['field_mpx_video_lede']['data'], site_json['api_path'], video_poster=poster)
        if lede_html:
            item['content_html'] += lede_html

        if page_json['attributes'].get('body'):
            body_soup = BeautifulSoup(page_json['attributes']['body']['processed'], 'html.parser')
        elif page_json['attributes'].get('field_article_body'):
            body_soup = BeautifulSoup(page_json['attributes']['field_article_body'][0]['processed'], 'html.parser')
        elif page_json['relationships'].get('field_paragraphs'):
            paragraphs = ''
            for data in page_json['relationships']['field_paragraphs']['data']:
                paragraphs += get_field_data(data, site_json['api_path'])
            body_soup = BeautifulSoup(paragraphs, 'html.parser')
        else:
            logger.warning('unknown body content in ' + item['url'])
            body_soup = None
        if body_soup:
            for el in body_soup.find_all('div', attrs={"data-embed-button": True}):
                new_html = ''
                if el['data-embed-button'] == 'media_entity_embed' or el['data-embed-button'] == 'social_media':
                    it = el.find(class_=re.compile(r'media--type-'))
                    if it:
                        if 'media--type-image' in it['class']:
                            new_html = get_field_data({"type": "media--image", "id": el['data-entity-uuid']}, site_json['api_path'])
                        elif 'media--type-twitter' in it['class']:
                            new_html = get_field_data({"type": "media--twitter", "id": el['data-entity-uuid']}, site_json['api_path'])
                        elif 'media--type-instagram' in it['class']:
                            new_html = get_field_data({"type": "media--instagram", "id": el['data-entity-uuid']}, site_json['api_path'])
                elif el['data-embed-button'] == 'mpx_video_embed':
                    new_html = get_field_data({"type": "media--mpx_video", "id": el['data-entity-uuid']}, site_json['api_path'])
                elif el['data-embed-button'] == 'teaser_embed':
                    el.decompose()
                    continue
                elif el['data-embed-button'] == 'media' and el.find(class_='editor_note__editor-note-text'):
                    it = el.find(class_='editor_note__editor-note-text')
                    new_html = it.decode_contents()
                elif el['data-embed-button'] == 'node' and el.get('data-entity-embed-display') and 'related_content' in \
                        el['data-entity-embed-display']:
                    el.decompose()
                    continue
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled data-embed-button {} in {}'.format(el['data-embed-button'], item['url']))

            for el in body_soup.find_all('div', class_='media'):
                new_html = ''
                if 'media--type-image' in el['class']:
                    it = el.find('img')
                    if it:
                        src = it['src']
                        if src.startswith('/'):
                            src = 'https://{}{}'.format(urlsplit(site_json['api_path']).netloc, src)
                        new_html = utils.add_image(src)
                elif 'media--type-youtube' in el['class']:
                    it = el.find('iframe')
                    if it:
                        query = parse_qs(urlsplit(it['src']).query)
                        src = query['url'][0]
                        new_html = utils.add_embed(src)
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled media {} in {}'.format(el['class'], item['url']))

            for el in body_soup.find_all('img', class_='figure-img'):
                # TODO: caption?
                new_html = utils.add_image(el['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                parents = el.find_parents()
                it = parents[-2]
                it.insert_after(new_el)
                it.decompose()

            for el in body_soup.find_all('picture'):
                it = el.find('source')
                if it and it.get('srcset'):
                    img_src = utils.image_from_srcset(it['srcset'], 1000)
                    it = el.next_sibling
                    if it.get('class') and 'article-img-meta' in it['class']:
                        caption = it.get_text()
                        it.decompose()
                    else:
                        caption = ''
                    new_html = utils.add_image(img_src, caption)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled picture in ' + item['url'])

            for el in body_soup.find_all('blockquote'):
                new_html = ''
                if el.get('class'):
                    if 'twitter-tweet' in el['class']:
                        links = el.find_all('a')
                        new_html = utils.add_embed(links[-1]['href'])
                    elif 'instagram-media' in el['class']:
                        new_html = utils.add_embed(el['data-instgrm-permalink'])
                else:
                    links = el.find_all('a')
                    if links and re.search(r'https://twitter\.com/[^/]+/status/\d+', links[-1]['href']):
                        new_html = utils.add_embed(links[-1]['href'])
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()

            for el in body_soup.find_all('iframe'):
                new_html = utils.add_embed(el['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                if el.parent and el.parent.name == 'p':
                    el.parent.insert_after(new_el)
                    el.parent.decompose()
                else:
                    el.insert_after(new_el)
                    el.decompose()

            for el in body_soup.find_all('script', attrs={"type": "application/json"}):
                i = el.string.find('{')
                j = el.string.rfind('}')
                if i > 0 and j > 0 and i != 1 and el.string[i:j+1].strip():
                    el_json = json.loads(el.string[i:j+1])
                    new_html = ''
                    if el_json.get('component') and el_json['component'] == 'InlineGallery':
                        for it in el_json['props']['media']:
                            if it['image']['src'].startswith('/'):
                                src = 'https://{}{}'.format(urlsplit(site_json['api_path']).netloc, it['image']['src'])
                            else:
                                src = it['image']['src']
                            new_html += utils.add_image(src)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    el.decompose()

            for el in body_soup.find_all('script'):
                el.decompose()

            for el in body_soup.find_all(id=re.compile(r'taboola')):
                el.decompose()

            item['content_html'] += str(body_soup)

            if page_json['relationships'].get('field_carousel_media') and page_json['relationships']['field_carousel_media'].get('data'):
                item['content_html'] += '<hr/><h2><u>GALLERY</u></h2>'
                for data in page_json['relationships']['field_carousel_media']['data']:
                    item['content_html'] += get_field_data(data, site_json['api_path'])

    elif page_json['type'] == 'article':
        # https://www.psychologytoday.com/us/articles/202309/inside-the-mind-of-a-hero
        if page_json['attributes'].get('subtitle'):
            item['content_html'] += '<p><em>{}</em></p>'.format(page_json['attributes']['subtitle'])

    elif page_json['type'] == 'blog_entry':
        # https://www.psychologytoday.com/us/blog/psych-unseen/202309/antipsychotic-therapy-since-the-1950s-little-has-changed
        if page_json['attributes'].get('field_blog_entry_subtitle'):
            item['content_html'] += '<p><em>{}</em></p>'.format(page_json['attributes']['field_blog_entry_subtitle'])
        if page_json['attributes'].get('field_key_points'):
            item['content_html'] += '<h4>Key points</h4><ul>'
            for it in page_json['attributes']['field_key_points']:
                item['content_html'] += '<li>{}</li>'.format(it)
            item['content_html'] += '</ul>'
        # TODO: content???
        if page_json['attributes'].get('field_references'):
            item['content_html'] += page_json['attributes']['field_references']['processed']

    if item.get('content_html'):
        item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # TODO: fiercevideo needs to use browser to load rss
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if '/rss' in split_url.path:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    n = 0
    feed_items = []
    feed = utils.init_jsonfeed(args)

    if site_json['api_path'].startswith(url):
        api_json = utils.get_url_json(site_json['api_path'] + 'node/article?sort=-created')
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        if api_json:
            for article in api_json['data']:
                article_url = 'https://{}{}'.format(urlsplit(site_json['api_path']).netloc, article['attributes']['path']['alias'])
                if save_debug:
                    logger.debug('getting content for ' + article_url)
                item = get_item(article, None, article_url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed_items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
            feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
            return feed

    urls = []
    page_html = utils.get_url_html(args['url'])
    soup = BeautifulSoup(page_html, 'html.parser')
    for el in soup.find_all(attrs={"role": "article"}):
        if el.get('class') and ('node--type-homepage' in el['class'] or 'node--type-external-links' in el['class']):
            continue
        if el.get('about'):
            url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, el['about'])
            if url not in urls:
                urls.append(url)

    for url in urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
