import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, unquote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    xhr_url = utils.clean_url(url)
    if xhr_url.endswith('/'):
        xhr_url += 'xhr/?showTaboola=true'
    else:
        xhr_url += '/xhr/?showTaboola=true'
    article_json = utils.get_url_json(xhr_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://www.cbssports.com' + article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['trackingData']['articlePubDate']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    if article_json['trackingData'].get('articleAuthorName'):
        item['authors'] = [{"name": x} for x in article_json['trackingData']['articleAuthorName']]
    elif article_json['trackingData'].get('contentOrigin'):
        item['authors'] = [{
            "name": article_json['trackingData']['contentOrigin']
        }]
    else:
        item['authors'] = [{
            "name": "CBSSports"
        }]
    item['author'] = {
        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
    }

    item['tags'] = article_json['trackingData']['topicName'].copy()

    soup = BeautifulSoup(article_json['template'], 'html.parser')
    article_body = soup.find(id='Article-body')
    if save_debug:
        utils.write_file(str(article_body), './debug/debug.html')

    item['content_html'] = ''
    el = soup.find(class_='Article-subline')
    if el:
        item['summary'] = el.get_text().strip()
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    el = soup.find(attrs={"itemprop": "image"})
    if el:
        it = el.find('meta', attrs={"itemprop": "url"})
        item['image'] = it['content']
        item['content_html'] += utils.add_image(item['image'])

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    el = article_body.find(class_='VideoHero')
    if el:
        it = el.find(id=re.compile(r'VideoPlayer-[a-f0-9]+'))
        player_json = json.loads(it['data-avia-video-player-options'])
        video_json = json.loads(player_json['videoDataJson'])
        if save_debug:
            utils.write_file(video_json, './debug/video.json')

    body_content = article_body.find(class_='Article-bodyContent')
    for el in body_content.find_all('native_placeholder'):
        el.decompose()

    for el in body_content.find_all(class_='GamblingPicks'):
        el.decompose()

    for el in body_content.find_all('span', class_='link'):
        el.unwrap()

    for el in body_content.find_all('span', class_='delete'):
        el.unwrap()

    for el in body_content.find_all(class_='icon-moon-caret-up'):
        el.string = '▲'
        el.unwrap()

    for el in body_content.find_all(class_='icon-moon-caret-down'):
        el.string = '▼'
        el.unwrap()

    for el in body_content.find_all('blockquote'):
        if not el.get('class'):
            new_html = utils.add_blockquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

    for el in body_content.find_all(class_='ArticleContentTable'):
        it = el.find('table')
        el.replace_with(it)

    for el in body_content.find_all('table'):
        el.attrs = {}
        if el.find(class_='PlayerObjectCell'):
            el['style'] = 'width:100%;'
            row_style = ''
        else:
            el['style'] = 'width:90%; margin-left:auto; margin-right:auto; border-collapse:collapse; border-top:1px solid light-dark(#333,#ccc);'
            row_style = 'border-bottom:1px solid light-dark(#333,#ccc);'
        for it in el.find_all(['thead', 'tr']):
            it.attrs = {}
            it['style'] = row_style
        for it in el.find_all(['th', 'td']):
            it.attrs = {}
            it['style'] = 'text-align:left; padding:8px;'
            if it.p:
                it.p.unwrap()

    for el in body_content.find_all(class_='TeamLogoNameLockup'):
        it = el.find('img', class_='TeamLogo-image')
        new_html = '<img src="{}" style="height:1em;"/>'.format(it['data-lazy'])
        it = el.find('span', class_='TeamName')
        new_html += '&nbsp;<a href="{}">{}</a>'.format(it.a['href'], it.a.get_text())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in body_content.find_all(class_='shortcode'):
        if el.find('section', class_='Newsletter-container'):
            el.decompose()
        else:
            logger.warning('unhandled shortcode section')

    for el in body_content.find_all(class_='MediaShortcode'):
        new_html = ''
        if 'MediaShortcodeImage' in el['class']:
            it = el.find(class_='MediaShortcodeImage-image')
            if it and it.get('data-large'):
                img_src = it['data-large']
            else:
                it = el.find('img')
                img_src = it['data-lazy']
            captions = []
            it = el.find(class_='MediaShortcode-caption')
            if it:
                caption = it.get_text().strip()
                if caption:
                    captions.append(caption)
            it = el.find(class_='MediaShortcode-credit')
            if it:
                caption = it.get_text().strip()
                if caption:
                    captions.append(caption)
            caption = ' | '.join(captions)
            new_html = utils.add_image(img_src, caption)
        elif 'MediaShortcodeYoutube-Video' in el['class']:
            it = el.find('iframe')
            new_html = utils.add_embed(it['src'])
        elif 'MediaShortcodeTwitter-Tweet' in el['class']:
            it = el.find_all('a')
            new_html = utils.add_embed(it[-1]['href'])
        elif 'MediaShortcodeInstagram' in el['class']:
            it = el.find('blockquote', class_='instagram-media')
            new_html = utils.add_embed(it['data-instgrm-permalink'])
        elif 'MediaShortcodeIframe' in el['class']:
            it = el.find('iframe')
            new_html = utils.add_embed(it['src'])
        else:
            logger.warning('unhandled MediaShortcode' + str(el['class']))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

    for el in body_content.find_all(attrs={"data-shortcode": True}):
        if el['data-shortcode'] == 'mtechprtcomponent':
            el.decompose()
        else:
            logger.warning('unhandled data-shortcode {} in {}'.format(el['data-shortcode'], item['url']))

    for el in body_content.find_all(class_='PlayerObjectCell'):
        new_html = ''
        it = el.find(class_='PlayerObjectV4Pick-roundPickInfo')
        if it:
            new_html += '<div style="margin-bottom:8px; padding:4px; background-color:#ccc; font-weight:bold;">' + it.get_text().strip() + '</div>'
        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; font-size:0.8em;">'
        if el.find(class_='PlayerObjectV4-nameBox'):
            new_html += '<div style="flex:1; text-align:center;"><div>'
            it = el.select('div.PlayerObjectV4-nameBox > div.PlayerObjectV4-logoNameLockup > div.HeadshotAndLogoLockup > div.HeadshotAndLogoLockup-logo img.TeamLogo-image')
            if it:
                new_html += '<img src="{}" style="width:64px;">'.format(it[0]['data-lazy'])
            it = el.select('div.PlayerObjectV4-nameBox > div.PlayerObjectV4-logoNameLockup > div.HeadshotAndLogoLockup > div.HeadshotAndLogoLockup-headshot figure.Headshot-image > img')
            if it:
                new_html += '<img src="{}" style="width:64px;">'.format(it[0]['data-lazy'])
            new_html += '</div><div>'
            it = el.select('div.PlayerObjectV4-nameBox > div.PlayerObjectV4-player > div.PlayerObjectV4-playerName > span.PlayerName')
            if it:
                new_html += '<span style="font-size:1.2em; font-weight:bold;">' + it[0].decode_contents() + '</span>'
            it = el.select('div.PlayerObjectV4-nameBox > div.PlayerObjectV4-player > div.PlayerObjectV4-playerName > span.PlayerObjectV4-playerPosition')
            if it:
                new_html += ' <span style="color:#555;">' + it[0].decode_contents() + '</span>'
            new_html += '</div>'
            it = el.select('div.PlayerObjectV4-nameBox > div.PlayerObjectV4-player > div.PlayerObjectV4-playerInfo')
            if it:
                new_html += it[0].decode_contents()
            new_html += '</div>'
        if el.find(class_='PlayerObjectV4-playerStatBox'):
            new_html += '<div style="flex:2;">'
            for it in el.select('div.PlayerObjectV4-playerStatBox > div:is(.PlayerObjectV4-playerStatRow, .PlayerObjectV4-playerStatNewRow) > table'):
                it.attrs = {}
                it['style'] = 'width:100%;'
                for x in el.find_all('h6', class_='PlayerObjectV4-label'):
                    x.attrs = {}
                    x.name = 'div'
                for x in el.find_all(['thead', 'tr']):
                    x.attrs = {}
                new_html += str(it) + '<!-- -->'
            it = el.select('div.PlayerObjectV4-playerStatBox > div.PlayerObjectV4-analysis')
            if it:
                new_html += '<p>' + it[0].decode_contents() + '</p>'
            new_html += '</div>'
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in body_content.find_all(class_='PlayerSnippet'):
        new_html = '<table><tr><td>'
        it = el.find('figure', class_='Headshot-image')
        if it:
            new_html += '<img src="{}" style="width:80px;"/></td><td>'.format(it.img['data-lazy'])
        else:
            new_html += '<img src="{}/image?width=80&height=80&mask=circle" style="width:80px;"/></td><td>'.format(config.server)
        it = el.find('a', class_='PlayerSnippet-name')
        if it:
            new_html += '<a href="{}"><strong>{}</strong></a>'.format(it['href'], it.get_text())
        else:
            it = el.find('span', class_='PlayerSnippet-name')
            new_html += '<strong>{}</strong>'.format(it.get_text())
        it = el.find(class_='PlayerSnippet-summary')
        if it:
            new_html += '<br/><small>{}</small>'.format(re.sub(r'\s+', '', it.get_text()).replace('\u2022', '&nbsp;&bull;&nbsp;'))
        if el.find(class_='PlayerSnippet-stats'):
            new_html += '<br/><table><tr>'
            for it in el.find_all(class_='PlayerSnippet-statLabel'):
                new_html += '<td><small>{}</small></td>'.format(it.get_text())
            new_html += '</tr><tr>'
            for it in el.find_all(class_='PlayerSnippet-statValue'):
                new_html += '<td><strong>{}</strong></td>'.format(it.get_text())
            new_html += '</tr></table>'
        new_html += '</td></tr></table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in body_content.find_all(class_='iframe'):
        it = el.find('iframe')
        new_html = utils.add_embed(it['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in body_content.select('a:has(> div.ArticleShortcode-container)'):
        new_html = utils.add_embed(el['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in body_content.find_all('a'):
        href = el['href']
        if href.startswith('/'):
            href = 'https://www.cbssports.com' + href
        el.attrs  = {}
        el['href'] = href

    item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', body_content.decode_contents())
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.cbssports.com/xml/rss
    if '/rss/' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')

    feed_urls = []
    if '/writers/' in args['url']:
        el = soup.find(id="authorArticles")
        if not el:
            return None
        for it in el.find_all('a'):
            if it['href'].startswith('/'):
                feed_urls.append('https://www.cbssports.com' + it['href'])
    elif '/teams/' in args['url']:
        el = soup.find('ul', class_="NewsFeed-list")
        if not el:
            return None
        for it in el.find_all(class_='NewsFeed-title'):
            feed_urls.append('https://www.cbssports.com' + it.a['href'])
    else:
        return None

    feed = utils.init_jsonfeed(args)
    feed['title'] = soup.title.get_text()
    feed_items = []
    for url in feed_urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


def test_handler():
    feeds = ['https://www.cbssports.com/rss/headlines/',
             'https://www.cbssports.com/rss/headlines/mlb',
             'https://www.cbssports.com/rss/headlines/nba',
             'https://www.cbssports.com/rss/headlines/nfl',
             'https://www.cbssports.com/rss/headlines/nhl',
             'https://www.cbssports.com/nfl/teams/CLE/cleveland-browns/',
             'https://www.cbssports.com/writers/mike-axisa/']
    for url in feeds:
        get_feed({"url": url}, True)
