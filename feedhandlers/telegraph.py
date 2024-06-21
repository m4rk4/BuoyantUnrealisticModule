import copy, html, json, math, pygal, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')

    article_json = None
    liveblog_json = None
    for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string.replace('\n', '').replace('\r', ''))
        if ld_json.get('@type'):
            if ld_json['@type'] == 'NewsArticle':
                article_json = ld_json
            elif ld_json['@type'] == 'LiveBlogPosting':
                liveblog_json = ld_json
    if save_debug:
        # utils.write_file(article_json, './debug/debug.json')
        utils.write_file(liveblog_json, './debug/debug.json')

    if liveblog_json and not article_json:
        article_json = liveblog_json

    item = {}
    if article_json and article_json.get('url'):
        item['url'] = article_json['url']
    else:
        el = page_soup.find('link', attrs={"rel": "canonical"})
        if el:
            item['url'] = el['href']
        else:
            item['url'] = url

    el = page_soup.find('meta', attrs={"name": "tmgads.articleid"})
    if el:
        item['id'] = el['content']
    elif article_json.get('mainEntityOfPage'):
        item['id'] = article_json['mainEntityOfPage']['@id']
    elif article_json.get('url'):
        item['id'] = article_json['url']
    else:
        item['id'] = item['url']

    item['title'] = article_json['headline']
    if '&#' in item['title']:
        item['title'] = html.unescape(item['title'])

    if liveblog_json:
        dt = datetime.fromisoformat(liveblog_json['liveBlogUpdate'][-1]['datePublished']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(liveblog_json['liveBlogUpdate'][0]['datePublished']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()
    elif article_json.get('datePublished'):
        dt = datetime.fromisoformat(article_json['datePublished']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if article_json.get('dateModified'):
            dt = datetime.fromisoformat(article_json['dateModified']).astimezone(timezone.utc)
            item['date_modified'] = dt.isoformat()
    else:
        el = page_soup.find('time', attrs={"itemprop": "datePublished"})
        if el:
            dt = datetime.fromisoformat(el['datetime']).astimezone(timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

    authors = []
    if article_json.get('author'):
        for it in article_json['author']:
            authors.append(it['name'])
    else:
        el = page_soup.find('meta', attrs={"name": "DCSext.author"})
        if el and el.get('content'):
            authors = [it.strip() for it in el['content'].split(';')]
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('publisher'):
        item['author'] = {"name": article_json['publisher']['name']}
    else:
        el = page_soup.find('meta', attrs={"property": "og:site_name"})
        if el and el.get('content'):
            item['author'] = {"name": el['content']}

    if article_json.get('keywords'):
        item['tags'] = article_json['keywords'].split(',')
    else:
        el = page_soup.find('meta', attrs={"name": "keywords"})
        if el:
            item['tags'] = el['content'].split(',')

    item['content_html'] = ''

    el = page_soup.find('p', attrs={"data-test": "standfirst"})
    if el:
        item['summary'] = el.get_text()
        item['content_html'] += '<p><em>' + el.decode_contents() + '</em></p>'

    if article_json.get('image'):
        item['_image'] = utils.clean_url(article_json['image'][0]['url']) + '?imwidth=1200'
    else:
        el = page_soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = utils.clean_url(el['content']) + '?imwidth=1200'

    el = page_soup.find('div', class_=['tpl-article__lead-asset', 'tpl-live-blog__lead-asset'])
    if el:
        if el.find(class_='video-player'):
            it = el.find(class_='video-player__source')
            item['content_html'] += utils.add_embed('https://www.youtube.com/embed/' + it['data-video'])
        elif el.find(class_='article-body-image'):
            it = el.find('meta', attrs={"itemprop": "url"})
            img_src = 'https://www.telegraph.co.uk' + it['content'] + '?imwidth=1200'
            captions = []
            it = el.find(attrs={"itemprop": "caption"})
            if it:
                captions.append(it.decode_contents().strip())
            it = el.find(attrs={"itemprop": "copyrightHolder"})
            if it:
                captions.append(it.get_text().strip())
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
    elif article_json.get('image'):
        captions = []
        if article_json['image'][0].get('description'):
            captions.append(article_json['image'][0]['description'])
        if article_json['image'][0].get('creditText'):
            captions.append('Credit : ' + article_json['image'][0]['creditText'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    body = page_soup.find('div', attrs={"itemprop": "articleBody"})
    if not body:
        body = page_soup.find('div', attrs={"itemprop": "reviewBody"})
        if body:
            el = page_soup.find('div', attrs={"itemprop": "reviewRating"})
            if el:
                it = el.find('meta', attrs={"itemprop": "ratingValue"})
                if it:
                    item['content_html'] += '<div style="font-size:2em; text-align:center;">'
                    for i in range(math.floor(float(it['content']))):
                        item['content_html'] += '★'
                    if it['content'].endswith('.5'):
                        item['content_html'] += '<div style="display:inline-block; position:relative; margin:0 auto; text-align:center;"><div style="display:inline-block; background:linear-gradient(to right, red 50%, white 50%); background-clip:text; -webkit-text-fill-color:transparent;">★</div><div style="position:absolute; top:0; width:100%">☆</div></div>'
                    for i in range(5 - math.ceil(float(it['content']))):
                        item['content_html'] += '☆'
                    item['content_html'] += '</div>'

    for el in page_soup.find_all(class_='live-post'):
        body.append(copy.copy(el))

    if body:
        # utils.write_file(str(body), './debug/body.html')
        for el in body.find_all('blockquote', class_=False):
            el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

        for el in body.find_all(class_='articleBodyText'):
            for it in el.find_all(class_='article-body-text'):
                if 'article-body-text--drop-cap' in it['class']:
                    p = it.find('p')
                    new_html = re.sub(r'>("?\w)', r'><span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', str(p), 1)
                    new_html += '<span style="clear:left;"></span>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    p.replace_with(new_el)
                it.unwrap()
            el.unwrap()

        for el in body.find_all('div', class_='articleBodyImage'):
            new_html = ''
            it = el.find(class_='article-body-image-image')
            if it:
                img_src = utils.clean_url('https://www.telegraph.co.uk' + it['data-src']) + '?imwidth=1200'
                captions = []
                it = el.find(attrs={"itemprop": "caption"})
                if it:
                    captions.append(it.decode_contents().strip())
                it = el.find(attrs={"itemprop": "copyrightHolder"})
                if it:
                    captions.append(it.get_text().strip())
                new_html = utils.add_image(img_src, ' | '.join(captions))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled articleBodyImage in ' + item['url'])

        for el in body.find_all('figure', class_='article-body-image'):
            new_html = ''
            it = el.find('meta', attrs={"itemprop": "url"})
            if it:
                img_src = 'https://www.telegraph.co.uk' + it['content'] + '?imwidth=1200'
                captions = []
                it = el.find(attrs={"itemprop": "caption"})
                if it:
                    captions.append(it.decode_contents().strip())
                it = el.find(attrs={"itemprop": "copyrightHolder"})
                if it:
                    captions.append(it.get_text().strip())
                new_html = utils.add_image(img_src, ' | '.join(captions))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled article-body-image in ' + item['url'])

        for el in body.find_all(class_='video-player'):
            new_html = ''
            it = el.find(class_='video-player__source')
            if it:
                new_html = utils.add_embed('https://www.youtube.com/embed/' + it['data-video'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled video-player in ' + item['url'])

        for el in body.find_all(class_='html-embed'):
            new_html = ''
            if el.find(class_='live-stream__post-wrapper'):
                it = el.find(class_='live-stream__post-wrapper')
                it.unwrap()
                el.unwrap()
                continue

            elif el.find(class_='twitter-tweet'):
                links = el.blockquote.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])

            elif el.find(class_='instagram-media'):
                new_html = utils.add_embed(el.blockquote['data-instgrm-permalink'])

            elif el.find('script', src=re.compile(r'author-hack')):
                el.decompose()
                continue

            elif el.find('script', string=re.compile(r'TelegraphPulse')):
                it = el.find('script', string=re.compile(r'TelegraphPulse'))
                m = re.search(r'TelegraphPulse\.drawChart\(["\'][^"\']+["\'],["\']([^"\']+)["\']', it.string)
                if m:
                    # print(m.group(1))
                    chart_json = utils.get_url_json('https://tmgpulse.azureedge.net/TmgApi/Snapshot/' + m.group(1))
                    if chart_json:
                        m = re.search(r'"title":"([^"]+)"', it.string)
                        if m:
                            title = m.group(1)
                        else:
                            title = chart_json['result']['model']['displayName']
                        new_html += '<table style="width:100%; border-collapse:collapse;"><tr style="line-height:1.5em; color:white; background-color:#555; border-bottom:1px solid #555;"><th colspan="4">{}</th></tr>'.format(title)
                        new_html += '<tr style="line-height:1.5em; background-color:#ccc; border-bottom:1px solid #ccc;"><th style="text-align:center;">Prev close</th><th  style="text-align:center;">Last</th><th  style="text-align:center;">1 day</th><th  style="text-align:center;">1 wk</th></tr><tr style="line-height:1.5em; border-bottom:1px solid #ccc;">'
                        new_html += '<td style="text-align:center;">{:.6g}</td>'.format(chart_json['result']['data']['prev'][4])
                        new_html += '<td style="text-align:center;">{:.6g}</td>'.format(chart_json['result']['data']['values']['c']['current'])
                        val = chart_json['result']['data']['values']['d']['current']
                        if val > 0:
                            color = ' color:green;'
                        elif val < 0:
                            color = ' color:red;'
                        else:
                            color = ''
                        new_html += '<td style="text-align:center;{}">{:+.4g}%</td>'.format(color, val)
                        val = chart_json['result']['data']['values']['w']['current']
                        if val > 0:
                            color = ' color:green;'
                        elif val < 0:
                            color = ' color:red;'
                        else:
                            color = ''
                        new_html += '<td style="text-align:center;{}">{:+.4g}%</td>'.format(color, val)
                        new_html += '<tr style="line-height:1.5em; background-color:#ccc; border-bottom:1px solid #ccc;"><th style="text-align:center;">1 mo</th><th style="text-align:center;">3 mo</th><th style="text-align:center;">YTD</th><th style="text-align:center;">1 yr</th></tr><tr style="line-height:1.5em; border-bottom:1px solid #ccc;">'
                        val = chart_json['result']['data']['values']['m']['current']
                        if val > 0:
                            color = ' color:green;'
                        elif val < 0:
                            color = ' color:red;'
                        else:
                            color = ''
                        new_html += '<td style="text-align:center;{}">{:+.4g}%</td>'.format(color, val)
                        val = chart_json['result']['data']['values']['m3']['current']
                        if val > 0:
                            color = ' color:green;'
                        elif val < 0:
                            color = ' color:red;'
                        else:
                            color = ''
                        new_html += '<td style="text-align:center;{}">{:+.4g}%</td>'.format(color, val)
                        val = chart_json['result']['data']['values']['ytd']['current']
                        if val > 0:
                            color = ' color:green;'
                        elif val < 0:
                            color = ' color:red;'
                        else:
                            color = ''
                        new_html += '<td style="text-align:center;{}">{:+.4g}%</td>'.format(color, val)
                        val = chart_json['result']['data']['values']['y']['current']
                        if val > 0:
                            color = ' color:green;'
                        elif val < 0:
                            color = ' color:red;'
                        else:
                            color = ''
                        new_html += '<td style="text-align:center;{}">{:+.4g}%</td>'.format(color, val)
                        new_html += '</tr></table>'
                        chart_data = []
                        if len(chart_json['result']['data']['minuteticks']) > 1:
                            for i in range(len(chart_json['result']['data']['minuteticks'])):
                                if i == 0:
                                    dt = datetime.fromtimestamp(chart_json['result']['data']['minuteticks'][0][0])
                                else:
                                    dt = datetime.fromtimestamp(chart_json['result']['data']['minuteticks'][0][0] + chart_json['result']['data']['minuteticks'][i][0])
                                chart_data.append((dt, chart_json['result']['data']['minuteticks'][i][1]))
                            line_chart = pygal.DateTimeLine(show_legend=False,
                                x_label_rotation=35, truncate_label=-1,
                                x_value_formatter=lambda dt: dt.strftime('%I:%M:%S %p'))
                            line_chart.add(chart_json['result']['model']['displayName'], chart_data)
                        else:
                            # Plot last 5 days
                            for i in range(-4, 0, 1):
                                dt = datetime.fromtimestamp(chart_json['result']['data']['history'][i][0])
                                chart_data.append((dt, chart_json['result']['data']['history'][i][4]))
                            dt = datetime.fromtimestamp(chart_json['result']['data']['xt'][0])
                            chart_data.append((dt, chart_json['result']['data']['xt'][4]))
                            line_chart = pygal.Line(show_legend=False, x_label_rotation=35, truncate_label=-1)
                            line_chart.x_labels = map(lambda d: d.strftime('%b %d'), [i[0] for i in chart_data])
                            line_chart.add('', [i[1] for i in chart_data])
                        chart_svg = line_chart.render(is_unicode=True)
                        new_html += '<figure style="margin:0; padding:0;">' + chart_svg + '<figcaption><small><a href="https://www.telegraph.co.uk{}">Find more information on the Telegraph</a></small></figcaption></figure>'.format(chart_json['result']['model']['investorUrl'])

            elif el.find(class_='tmg-particle'):
                it = el.find(['iframe', 'aside'])
                if 'autoplay-video' in it['class']:
                    particle_html = utils.get_url_html(it['src'])
                    if particle_html:
                        particle_soup = BeautifulSoup(particle_html, 'lxml')
                        particle_el = particle_soup.find('script', string=re.compile(r'window\.videos'))
                        video_src = ''
                        m = re.search(r'"url":"([^"]+\.m3u8)"', particle_el.string)
                        if m:
                            video_src = m.group(1)
                            video_type = 'application/x-mpegURL'
                        else:
                            m = re.search(r'"url":"([^"]+\.mp4)"', particle_el.string)
                            if m:
                                video_src = m.group(1)
                                video_type = 'video/mp4'
                        m = re.search(r'"thumbnail":"([^"]+)"', particle_el.string)
                        if m:
                            poster = m.group(1)
                        else:
                            poster = ''
                        particle_el = particle_soup.find(attrs={"data-widget-title": True})
                        if particle_el:
                            caption = particle_el['data-widget-title']
                        else:
                            caption = ''
                        if video_src:
                            new_html = utils.add_video(video_src, video_type, poster, caption)
                elif 'audio-player' in it['class']:
                    particle_html = utils.get_url_html(it['src'])
                    if particle_html:
                        particle_soup = BeautifulSoup(particle_html, 'lxml')
                        audio = particle_soup.find('audio')
                        if audio:
                            particle_el = particle_soup.find('img', class_='audio-player__album-art--mini-square')
                            if particle_el:
                                poster = '{}/image?url={}&overlay=audio'.format(config.server, quote_plus(particle_el['src']))
                            else:
                                poster = '{}/image?width=128&height=128&overlay=audio'.format(config.server)
                            new_html += '<table style="width:100%;"><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;" /></a></td><td style="vertical-align:top;">'.format(audio['src'], poster)
                            particle_el = particle_soup.find(class_='particle-header')
                            if particle_el:
                                new_html += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(audio['src'], particle_el.get_text())
                            particle_el = particle_soup.find(class_='particle-subheader')
                            if particle_el:
                                new_html += '<div style="font-size:0.9em;">{}</div>'.format(particle_el.get_text())
                            new_html += '</td></tr></table>'
                elif 'embed' in it['class'] and it.name == 'aside':
                    img_src = '{}/screenshot?url={}&locator=section%23particle&networkidle=true'.format(config.server, quote_plus(it['data-html-uri']))
                    new_html = utils.add_image(img_src, it.get('title'), link=it['data-html-uri'])
                elif 'embed' in it['class']:
                    particle_html = utils.get_url_html(it['src'])
                    if particle_html:
                        particle_soup = BeautifulSoup(particle_html, 'lxml')
                        if particle_soup.find(class_='liveblog-views'):
                            new_html = '<div>'
                            particle_el = particle_soup.select('div.liveblog-views > div.liveblog-img > img')
                            if particle_el:
                                new_html += '<img style="float:left; margin-right:8px;" src="{}/image?url={}&height=48&width=48&mask=ellipse"/>'.format(config.server, quote_plus(particle_el[0]['src']))
                            particle_el = particle_soup.select('div.liveblog-views > div.liveblog-textblock > div.auth-name')
                            if particle_el:
                                new_html += particle_el[0].decode_contents()
                            particle_el = particle_soup.select('div.liveblog-views > div.liveblog-textblock > div.analysis-tag')
                            if particle_el:
                                new_html += '<br/><small>{}</small>'.format(particle_el[0].decode_contents())
                            new_html += '</div>'
                            if 'float:' in new_html:
                                new_html += '<div style="clear:left;"></div>'
                        else:
                            img_src = '{}/screenshot?url={}&locator=section%23particle&networkidle=true'.format(config.server, quote_plus(it['src']))
                            new_html = utils.add_image(img_src, it.get('title'), link=it['src'])
                elif 'illustrator-embed' in it['class'] or 'sport-widget' in it['class'] or 'opta-widget-v3' in it['class']:
                    if it.get('src'):
                        img_src = '{}/screenshot?url={}&locator=section%23particle&networkidle=true'.format(config.server, quote_plus(it['src']))
                        new_html = utils.add_image(img_src, it.get('title'), link=it['src'])
                    elif it.get('data-html-uri'):
                        img_src = '{}/screenshot?url={}&locator=section%23particle&networkidle=true'.format(config.server, quote_plus(it['data-html-uri']))
                        new_html = utils.add_image(img_src, it.get('title'), link=it['data-html-uri'])
                    else:
                        logger.warning('unknown tmg-particle illustrator-embed src in ' + item['url'])
                elif 'image-comparison' in it['class']:
                    particle_html = utils.get_url_html(it['src'])
                    if particle_html:
                        particle_soup = BeautifulSoup(particle_html, 'lxml')
                        particle_el = particle_soup.find(class_='titles-header')
                        if it:
                            new_html += '<h3>' + particle_el.get_text().strip() + '</h3>'
                        new_html += '<div style="display:flex; flex-wrap:wrap; gap:4px;">'
                        particle_el = particle_soup.find('img', class_='img1')
                        new_html += '<div style="flex:1; min-width:256px; margin:auto;">' + utils.add_image(particle_el['src'], particle_el.get('alt')) + '</div>'
                        particle_el = particle_soup.find('img', class_='img2')
                        new_html += '<div style="flex:1; min-width:256px; margin:auto;">' + utils.add_image(particle_el['src'], particle_el.get('alt')) + '</div>'
                        particle_el = particle_soup.find('figcaption', class_='credit')
                        if particle_el:
                            new_html += '<div><small>' + particle_el.get_text().strip() + '</small></div>'
                        new_html += '</div>'
                elif 'timeline' in it['class']:
                    particle_html = utils.get_url_html(it['src'])
                    if particle_html:
                        particle_soup = BeautifulSoup(particle_html, 'lxml')
                        new_html = ''
                        particle_el = particle_soup.find(class_='particle__title')
                        if particle_el:
                            new_html += '<h2>' + particle_el.get_text().strip().encode('iso-8859-1').decode('utf-8') + '</h2>'
                        new_html += '<table style="width:90%; height:1px; margin:auto; border-collapse:collapse;">'
                        cards = particle_soup.select('div.timeline div.timeline__card > div.timeline__content')
                        for i, particle_el in enumerate(cards):
                            if i < len(cards) - 1:
                                new_html += '<tr style="height:100%;"><td style="height:100%; width:32px; padding:0; vertical-align:top;"><div style="display:grid; height:100%; padding:0;"><div style="grid-area:1/1; height:100%; width:14px; border-right: 4px solid #555;"></div><div style="grid-area:1/1; height:24px; width:24px; border-radius:50%; border:4px solid #555; background-color:#ccc;"></div></div></td><td style="height:100%; vertical-align:top; padding:8px 0 0 0;"><div style="width:0; height:0; border-top:8px solid transparent; border-right:16px solid #555; border-bottom:8px solid transparent;"></div></td><td style="padding:0;"><div style="color:white; background-color:#555; border-radius:6px; padding:10px 20px; margin-bottom:8px;">'
                            else:
                                new_html += '<tr style="height:100%;"><td style="height:100%; width:32px; padding:0; vertical-align:top;"><div style="display:grid; height:100%; padding:0;"><div style="grid-area:1/1; height:24px; width:24px; border-radius:50%; border:4px solid #555; background-color:#ccc;"></div></div></td><td style="height:100%; vertical-align:top; padding:8px 0 0 0;"><div style="width:0; height:0; border-top:8px solid transparent; border-right:16px solid #555; border-bottom:8px solid transparent;"></div></td><td style="padding:0;"><div style="color:white; background-color:#555; border-radius:6px; padding:10px 20px; margin-bottom:8px;">'
                            new_html += particle_el.decode_contents().encode('iso-8859-1').decode('utf-8')
                            new_html += '</div></td></tr>'
                        new_html += '</table>'
                elif 'table' in it['class']:
                    if it.get('src'):
                        particle_html = utils.get_url_html(it['src'])
                    elif it.get('data-html-uri'):
                        particle_html = utils.get_url_html(it['data-html-uri'])
                    else:
                        logger.warning('unknown tmg-particle table src in ' + item['url'])
                        particle_html = ''
                    if particle_html:
                        particle_soup = BeautifulSoup(particle_html, 'lxml')
                        if particle_soup.find(class_=re.compile(r'cst-table')):
                            particle_el = particle_soup.find(class_='particle__title')
                            if particle_el:
                                new_html += '<h3>' + particle_el.get_text().strip() + '</h3>'
                            new_html += '<table style="width:100%; border-collapse:collapse;">'
                            for row in particle_soup.find_all(class_='cst-table__row--header'):
                                new_html += '<tr style="border-bottom:1px solid #ccc;">'
                                for col in row.find_all(class_='grid-col'):
                                    new_html += '<th style="text-align:left;">' + col.decode_contents() + '</th>'
                                new_html += '</tr>'
                            for row in particle_soup.find_all(class_='cst-table__row'):
                                if 'cst-table__row--header' in row['class']:
                                    continue
                                new_html += '<tr style="border-bottom:1px solid #ccc;">'
                                for col in row.find_all(class_='grid-col'):
                                    new_html += '<td>' + col.decode_contents() + '</td>'
                                new_html += '</tr>'
                            new_html += '</table>'
                        elif particle_soup.find('table'):
                            particle_el = particle_soup.find(attrs={"data-type": "heading"})
                            if particle_el:
                                new_html += '<h3>' + particle_el.get_text().strip() + '</h3>'
                            particle_el = particle_soup.find('table')
                            particle_el['style'] = 'width:100%; border-collapse:collapse'
                            for col in particle_el.find_all('th'):
                                col.attrs = {}
                                col['style'] = 'text-align:left;'
                            for row in particle_el.find_all('tr'):
                                row.attrs = {}
                                row['style'] = 'border-bottom:1px solid #ccc;'
                            new_html += str(particle_el)
                elif 'vote' in it['class']:
                    particle_html = utils.get_url_html(it['src'])
                    vote_id = 'vote-' + it['id']
                    vote_json = utils.get_url_json('https://sets.eip.telegraph.co.uk/' + vote_id)
                    if particle_html and vote_json:
                        utils.write_file(vote_json, './debug/vote.json')
                        particle_soup = BeautifulSoup(particle_html, 'lxml')
                        particle_el = particle_soup.find('section', id='particle')
                        title = particle_soup.find(class_='vote-heading')
                        if title:
                            new_html += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(it['src'], title.get_text().encode('iso-8859-1').decode('utf-8'))
                        new_html += '<table style="margin-left:1em;">'
                        for i, vote_entry in enumerate(particle_soup.find_all(class_='vote-entry')):
                            new_html += '<tr>'
                            title = vote_entry.find(class_='text')
                            if title:
                                new_html += '<td>' + title.get_text().strip() + '</td>'
                            if vote_entry.name == 'button':
                                buttons = [vote_entry]
                            else:
                                buttons = vote_entry.find_all('button')
                            for n, button in enumerate(buttons):
                                new_html += '<td>'
                                if particle_el.get('data-vote-variant') and particle_el['data-vote-variant'] == 'Poll':
                                    uuid = 'Poll'
                                elif button.get('data-uuid'):
                                    uuid = button['data-uuid']
                                elif button.div and button.div.get('data-uuid'):
                                    uuid = button.div['data-uuid']
                                elif button.input and button.input.get('value'):
                                    uuid = button.input['value']
                                else:
                                    logger.warning('unknown vote uuid for ' + it['src'])
                                    uuid = ''
                                if uuid:
                                    if button.label:
                                        new_html += '●&nbsp;' + button.label.get_text() + ':&nbsp;'
                                    elif button.get('class') and 'upvote' in button['class']:
                                        new_html += '👍:&nbsp;'
                                    elif button.get('class') and 'downvote' in button['class']:
                                        new_html += '👎:&nbsp;'
                                    if len(buttons) > 1:
                                        vote = vote_json[vote_id][uuid][n]
                                    else:
                                        vote = vote_json[vote_id][uuid][i]
                                    new_html += '{} ({:.1f}%)'.format(vote['count'], 100*vote['share'])
                                new_html += '</td>'
                            new_html += '</tr>'
                        new_html += '</table>'
                elif 'breakout-box' in it['class']:
                    if it.get('src'):
                        particle_html = utils.get_url_html(it['src'])
                    elif it.get('data-html-uri'):
                        particle_html = utils.get_url_html(it['data-html-uri'])
                    if particle_html:
                        particle_soup = BeautifulSoup(particle_html, 'html.parser')
                        # particle_el = particle_soup.find(class_=['bb-header__title', 'header_title'])
                        # if particle_el:
                        #     new_html += '<h3>' + particle_el.decode_contents().encode('iso-8859-1').decode('utf-8') + '</h3>'
                        for particle_el in particle_soup.find_all('section', class_='component'):
                            if particle_el.table:
                                particle_el.table.attrs = {}
                                particle_el.table['style'] = 'width:100%; border-collapse:collapse'
                                for col in particle_el.table.find_all('th'):
                                    col.attrs = {}
                                    col['style'] = 'text-align:left;'
                                for row in particle_el.table.find_all('tr'):
                                    row.attrs = {}
                                    row['style'] = 'border-bottom:1px solid #ccc;'
                            new_html += particle_el.decode_contents().encode('iso-8859-1').decode('utf-8')
                        if new_html:
                            new_html = utils.add_blockquote(new_html)
                elif 'sticky-nav' in it['class']:
                    el.decompose()
                    continue

            elif el.find(class_='product-card__content'):
                link = el.find('a', class_='product-card__affiliate-cta__link')
                caption = link.get_text().strip()
                it = el.find(class_='product-card__affiliate-price__wrap')
                if it:
                    caption += ': ' + it.get_text().strip()
                it = el.find(class_='product-card__affiliate-summary__name')
                if it:
                    caption += ' at ' + it.get_text().strip()
                new_html = utils.add_button(link['href'], caption)

            elif el.find(class_=re.compile('universal-listing')):
                link = el.find('a', class_='call-to-action__link-manual')
                caption = link.get_text().strip()
                it = el.find(class_='e-price__wrapper-manual')
                if it:
                    if el.find(class_='universal-listing__price-from-manual'):
                        caption += ': From ' + it.get_text().strip()
                    else:
                        caption += ': ' + it.get_text().strip()
                new_html = utils.add_button(link['href'], caption)
                it = el.find(class_='product-card-signature')
                if it:
                    new_html += '<div style="font-size:0.6em; text-align:center;">' + it.decode_contents() + '</div>'
                new_html += '<div>&nbsp;</div>'

            elif el.find(class_=['cta-button', 'cta-disclaimer']):
                it = el.find(class_='cta-disclaimer')
                link = el.find('a', class_='cta-button')
                if it and not link:
                    link = it.find_previous_sibling('a')
                if link:
                    new_html += utils.add_button(link['href'], link.get_text(), 'black')
                    if it:
                        new_html += '<div style="font-size:0.6em; text-align:center;">' + it.decode_contents() + '</div>'

            elif el.find(class_=['DisclaimerShort', 'DisclaimerLong']):
                it = el.find(class_=['DisclaimerShort', 'DisclaimerLong'])
                new_html = utils.add_blockquote(it.decode_contents())

            elif el.find(class_=re.compile(r'everviz-')):
                it = el.find('script', attrs={"src": re.compile('app\.everviz\.com')})
                if it:
                    particle_html = utils.get_url_html(it['src'])
                    if particle_html:
                        m = re.search(r'var options = (\{.*?\});\s+var', particle_html)
                        if m:
                            options_json = json.loads(m.group(1))
                            utils.write_file(options_json, './debug/everviz.json')
                            x = []
                            y = []
                            for m in re.findall(r'("[^"]+"|[\d\.]+)(;|\s|$)', options_json['data']['csv']):
                                val = m[0].replace('"', '')
                                if val.replace('.', '').isnumeric():
                                    val = float(val)
                                elif re.search(r'^[\d/-]+$', val) and options_json['data'].get('dateFormat'):
                                    if options_json['data']['dateFormat'] == 'dd/mm/YYYY':
                                        val = datetime.strptime(val.replace('-', '/'), '%d/%m/%Y')
                                    elif options_json['data']['dateFormat'] == 'YYYY/mm/dd':
                                        val = datetime.strptime(val.replace('-', '/'), '%Y/%m/%d')
                                    else:
                                        logger.warning('unhandled everviz data date format in ' + item['url'])
                                if m[1] == ';':
                                    x.append(val)
                                else:
                                    y.append(val)
                            if isinstance(x[1], datetime):
                                line_chart = pygal.DateTimeLine(show_legend=False,
                                                    x_label_rotation=35, truncate_label=-1,
                                                    x_value_formatter=lambda dt: dt.strftime('%b %d %Y'))
                                line_chart.add(y[0], list(map(lambda a, b:(a,b), x[1:], y[1:])))
                            else:
                                line_chart = pygal.Line(show_legend=False,
                                                        x_label_rotation=35, truncate_label=-1)
                                line_chart.x_labels = x[1:]
                                line_chart.add(y[0], y[1:])
                            if options_json['xAxis'].get('title'):
                                line_chart.x_title = options_json['xAxis']['title']['text']
                            if options_json['yAxis'].get('title'):
                                line_chart.y_title = options_json['yAxis']['title']['text']
                            chart_svg = line_chart.render(is_unicode=True)
                            if options_json['title'].get('text'):
                                particle_el = BeautifulSoup(options_json['title']['text'], 'html.parser')
                                new_html += '<div style="font-size:1.1em; font-weight:bold;">' + particle_el.get_text().strip() + '</div>'
                            if options_json['subtitle'].get('text'):
                                particle_el = BeautifulSoup(options_json['subtitle']['text'], 'html.parser')
                                new_html += '<div style="font-size:0.9em;">' + particle_el.get_text().strip() + '</div>'
                            if options_json['credits'].get('text'):
                                particle_el = BeautifulSoup(options_json['credits']['text'], 'html.parser')
                                caption = '<figcaption><small>' + particle_el.get_text().strip() + '</small></figcaption>'
                            else:
                                caption = ''
                            new_html += '<figure style="margin:0; padding:0;">' + chart_svg + caption + '</figure>'

            elif el.find('iframe', attrs={"src": True}):
                new_html = utils.add_embed(el.iframe['src'])

            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled html-embed in ' + item['url'])

        for el in body.find_all(class_='live-post'):
            new_html = '<div>&nbsp;</div><hr style="border-top:2px solid #ccc;"><div>&nbsp;</div>'
            it = el.find(class_='live-post__wrapper-body-timestamp')
            if it and it.time:
                dt = datetime.fromisoformat(it.time['datetime']).astimezone(timezone.utc)
                new_html += '<div style="font-size:0.8em;">' + utils.format_display_date(dt) + '</div>'
            it = el.find(class_='live-post__title')
            if it:
                new_html += '<div style="font-size:1.1em; font-weight:bold;">' + it.decode_contents() + '</div>'
                it.decompose()
            it = el.find(class_='live-post__wrapper-body-article')
            if it:
                if re.search(r'^<(div|figure|table)', it.decode_contents().strip()):
                    new_html += '<div>&nbsp;</div>'
                new_html += it.decode_contents()
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in body.find_all(class_='article-body-text'):
            el.unwrap()

        for el in body.find_all(class_=['article-betting-unit-container', 'teaser']):
            el.decompose()

        item['content_html'] += body.decode_contents()
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(div|figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
