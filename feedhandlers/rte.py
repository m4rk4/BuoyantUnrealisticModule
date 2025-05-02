import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import datawrapper, rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    src = utils.clean_url(img_src)
    m = re.search(r'-\d+\.jpg$', src)
    if m:
        return re.sub(r'-\d+\.jpg$', '-{}.jpg'.format(width), src)
    return img_src


def add_rte_video(video_id):
    video_json = utils.get_url_json('https://www.rte.ie/rteavgen/getplaylist/?format=json&id=' + video_id)
    if not video_json:
        return ''
    video_src = video_json['shows'][0]['media:group'][0]['hls_server'] + video_json['shows'][0]['media:group'][0]['hls_url']
    return utils.add_video(video_src, 'application/x-mpegURL', video_json['shows'][0]['thumbnail'], video_json['shows'][0]['title'], use_proxy=True)


def add_comcast_video(video_id, video_guid):
    auth_token = utils.get_url_json('https://www.rte.ie/servicelayer/api/anonymouslogin?isocode=IE')
    if not auth_token:
        return ''
    video_html = utils.get_url_html('https://link.eu.theplatform.com/s/1uC-gC/media/{}/?auth={}&formats=mpeg-dash&format=smil&tracking=true"'.format(video_id, auth_token['mpx_token']))
    if not video_html:
        return ''
    video_soup = BeautifulSoup(video_html, 'html.parser')
    it = video_soup.find('meta', attrs={"name": "title"})
    if it:
        caption = it['content']
    else:
        caption = ''
    it = video_soup.find('ref')
    if not it:
        it = video_soup.find('video')
    if it:
        video_json = utils.get_url_json('https://feed.entertainment.tv.theplatform.eu/f/1uC-gC/prd-webplayer-programmes/?byGuid={}&fields=plprogram$pubDate,rte$station,plprogram$longTitle,plprogram$tags,plprogram$tvSeasonEpisodeNumber,plprogram$tvSeasonNumber,plprogramavailability$media.media$content.isProtected,plprogram$ratings,plprogramavailability$media.plmedia$availabilityTags,rte$defaultThumbnail'.format(video_guid))
        if video_json:
            poster = resize_image(video_json['entries'][0]['rte$defaultThumbnail'])
        else:
            poster = ''
        return utils.add_video(it['src'], it.get('type'), poster, caption)
    return ''


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    page_soup = BeautifulSoup(page_html, 'lxml')

    page_json = utils.get_url_json(utils.clean_url(url) + '?json')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')
    
    ld_json = None
    for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if isinstance(ld_json, dict) and ld_json['@type'] == 'NewsArticle':
            break
        ld_json = None

    if not ld_json:
        logger.warning('unable to find ld+json in ' + url)
        return None
    
    item = {}
    item['id'] = page_json['id']

    el = page_soup.find('link', attrs={"rel": "canonical"})
    if el:
        item['url'] = el['href']
    else:
        el = page_soup.find('meta', attrs={"property": "og:url"})
        if el:
            item['url'] = el['content']
        else:
            item['url'] = url

    item['title'] = html.unescape(ld_json['headline'])

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()
    elif page_json.get('date_modified'):
        dt = datetime.fromisoformat(page_json['date_modified'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": html.unescape(ld_json['author']['name'])
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if ld_json.get('keywords'):
        item['tags'] = [x.strip() for x in ld_json['keywords'].split(',')]
    else:
        for el in page_soup.select('ul.tags > li > a'):
            item['tags'].append(el.get_text().strip())
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    el = page_soup.find('figure', id='main-article-image')
    if el:
        item['image'] = el.img['src']
        if el.figcaption:
            caption = el.figcaption.decode_contents()
        else:
            caption = ''
        item['content_html'] += utils.add_image(resize_image(item['image']), caption)
    else:
        el = page_soup.select('div.article-meta + div.widget-container p[data-embed=\"rte-player\"] > iframe')
        if el and el[0].get('data-src'):
            params = parse_qs(urlsplit(el[0]['data-src']).query)
            if params and params.get('clipid'):
                item['content_html'] += add_rte_video(params['clipid'][0])

    if 'image' in item and ld_json.get('thumbnailUrl'):
        item['image'] = ld_json['thumbnailUrl']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    soup = BeautifulSoup(page_json['content'], 'html.parser')
    for el in soup.find_all('figure', class_='image'):
        if el.figcaption:
            caption = el.figcaption.decode_contents()
        else:
            caption = ''
        new_html = utils.add_image(resize_image(el.img['src']), caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(attrs={"data-embed": True}):
        new_html = ''
        if el['data-embed'] == 'rte-player':
            new_html = add_rte_video(el['data-id'])
        elif el['data-embed'] == 'comcast-player':
            new_html = add_comcast_video(el['data-id'], el['data-guid'])
        elif el['data-embed'] == 'flourish':
            new_html = utils.add_embed(el.iframe['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled data-embed {} in {}'.format(el['data-embed'], item['url']))

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
