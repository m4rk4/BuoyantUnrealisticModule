import html, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1].split('.')[0]
    ghost_url = '{}posts/slug/{}/?key={}&slug={}&include=authors%2Ctags'.format(site_json['data-api'], slug, site_json['data-key'], slug)
    ghost_json = utils.get_url_json(ghost_url)
    if not ghost_json:
        return None
    if save_debug:
        utils.write_file(ghost_json, './debug/debug.json')
    post_json = ghost_json['posts'][0]
    return get_item(post_json, args, site_json, save_debug)


def get_item(post_json, args, site_json, save_debug):
    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['url']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['published_at']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['updated_at']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in post_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for it in post_json['tags']:
        item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if post_json.get('html'):
        content_html = post_json['html'].replace('<!--kg-card-begin: html-->', '<div class="kg-card-begin">').replace('<!--kg-card-end: html-->', '</div>')
        soup = BeautifulSoup(content_html, 'html.parser')
        if save_debug:
            utils.write_file(str(soup), './debug/debug.html')
    else:
        soup = None

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    if post_json.get('custom_excerpt'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['custom_excerpt'])

    if post_json.get('feature_image'):
        item['_image'] = post_json['feature_image']
        if not soup or soup.find().name != 'figure':
            item['content_html'] += utils.add_image(item['_image'], post_json.get('feature_image_caption'))

    if soup:
        for el in soup.find_all('blockquote'):
            if not (el.get('class') and ('twitter-tweet' in el['class'] or 'instagram-media' in el['class'] or 'tiktok-embed' in el['class'])):
                new_html = utils.add_blockquote(el.decode_contents(), False)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in soup.find_all('pre'):
            el['style'] = 'margin-left:2em; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'

        for el in soup.find_all(class_=['kg-card', 'kg-card-begin']):
            if el.name == None:
                continue
            new_html = ''
            if 'kg-image-card' in el['class'] or ('kg-card-begin' in el['class'] and el.next_element.name == 'figure'):
                it = el.find('figcaption')
                if it:
                    caption = it.decode_contents()
                else:
                    caption = ''
                it = el.find('img')
                if it:
                    if it.get('srcset'):
                        img_src = utils.image_from_srcset(it['srcset'], 1000)
                    else:
                        img_src = it['src']
                    new_html = utils.add_image(img_src, caption)
                else:
                    it = el.find('iframe')
                    if it:
                        if caption:
                            new_html = utils.add_embed(it['src'], {"caption": caption})
                        else:
                            new_html = utils.add_embed(it['src'])
            elif 'kg-gallery-card' in el['class']:
                new_html = ''
                images = el.find_all(class_='kg-gallery-image')
                n = len(images) - 1
                for i, it in enumerate(images):
                    img = it.find('img')
                    if img:
                        if img.get('srcset'):
                            img_src = utils.image_from_srcset(img['srcset'], 1000)
                        else:
                            img_src = img['src']
                    if i < n:
                        new_html += utils.add_image(img_src)
                    else:
                        figcap = el.find('figcaption')
                        if figcap:
                            caption = figcap.decode_contents()
                        else:
                            caption = ''
                        new_html += utils.add_image(img_src, caption)
            elif 'kg-video-card' in el['class']:
                it = el.find('video')
                if it:
                    poster = it.get('poster')
                    if it.get('style'):
                        m = re.search(r'background:[^;]*?url\(\'([^\']+)\'\)', it['style'])
                        if m:
                            poster = m.group(1)
                    figcap = el.find('figcaption')
                    if figcap:
                        caption = figcap.decode_contents()
                    else:
                        caption = ''
                    new_html = utils.add_video(it['src'], 'video/mp4', poster, caption)
            elif 'kg-embed-card' in el['class']:
                if el.find(class_='twitter-tweet'):
                    links = el.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
                else:
                    it = el.find('iframe')
                    if it:
                        new_html = utils.add_embed(it['src'])
            elif 'kg-callout-card' in el['class']:
                new_html = '<div style="margin-top:1em; background:rgba(124,139,154,.13);">'
                it = el.find(class_='kg-callout-emoji')
                if it:
                    new_html += '<div style="float:left; display:inline-block; font-size:2em; margin-right:8px;">{}</div>'.format(it.get_text())
                it = el.find(class_='kg-callout-text')
                if it:
                    new_html += '<div style="overflow:hidden;">{}</div>'.format(it.decode_contents())
                new_html += '<div style="clear:left;"></div></div>'
            elif 'kg-bookmark-card' in el['class']:
                link = el.find('a', class_='kg-bookmark-container')
                new_html = '<table style="margin-left:1em; width:100%;"><tr>'
                it = el.find(class_='kg-bookmark-thumbnail')
                if it:
                    new_html += '<td style="width:200px;"><a href="{}"><img src="{}" style="width:200px;" /></a></td>'.format(link['href'], it.img['src'])
                new_html += '<td>'
                it = el.find(class_='kg-bookmark-title')
                if it:
                    new_html += '<a href="{}"><span style="font-size:1.1em; font-weight:bold;">{}</span></a>'.format(link['href'], it.get_text())
                it = el.find(class_='kg-bookmark-description')
                if it:
                    new_html += '<br/><small>{}</small>'.format(it.get_text())
                if el.find(class_='kg-bookmark-metadata'):
                    new_html += '<br/>'.format(it.get_text())
                    it = el.find('img', class_='kg-bookmark-icon')
                    if it:
                        new_html += '<img src="{}" style="float:left; height:1em;"/>&nbsp;'.format(it['src'])
                    new_html += '<small>'
                    it = el.find(class_='kg-bookmark-author')
                    if it:
                        new_html += it.get_text()
                    it = el.find(class_='kg-bookmark-publisher')
                    if it:
                        new_html += '&nbsp;&bull;&nbsp;' + it.get_text()
                    new_html += '</small>'
                new_html += '</td></tr></table>'
            elif 'kg-product-card' in el['class']:
                link = el.find('a', class_='kg-product-card-button')
                new_html = '<table style="margin-left:1em; width:100%;"><tr>'
                it = el.find('img', class_='kg-product-card-image')
                if it:
                    new_html += '<td style="width:200px;"><a href="{}"><img src="{}" style="width:200px;" /></a></td>'.format(link['href'], it['src'])
                new_html += '<td>'
                it = el.find(class_='kg-product-card-title')
                if it:
                    new_html += '<a href="{}"><span style="font-size:1.1em; font-weight:bold;">{}</span></a>'.format(link['href'], it.get_text())
                it = el.find(class_='kg-product-card-rating')
                if it:
                    new_html += '<br/>'
                    for star in it.find_all(class_='kg-product-card-rating-star'):
                        new_html += '&#9733;'
                it = el.find(class_='kg-product-card-description')
                if it:
                    new_html += '<div style="font-size:0.9em;">{}</div>'.format(it.decode_contents())
                new_html += '</td></tr></table>'
            elif 'kg-header-card' in el['class']:
                el.attrs = {}
                el['style'] = 'text-align:center;'
                for it in el.find(class_=re.compile(r'kg-header-card')):
                    it.attrs = {}
                continue
            elif 'kg-button-card' in el['class']:
                it = el.find(class_='kg-btn')
                if it:
                    it['style'] = 'color:white;'
                    new_html += '<div style="text-align:center;"><div style="display:inline-block; padding:1em; background-color:#5928ED; text-align:center;">{}</div></div>'.format(str(it))
            elif el.find(class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif el.find('blockquote', class_='instagram-media'):
                it = el.find('blockquote', class_='instagram-media')
                if it:
                    new_html = utils.add_embed(it['data-instgrm-permalink'])
            elif el.find('blockquote', class_='tiktok-embed'):
                it = el.find('blockquote', class_='tiktok-embed')
                if it:
                    new_html = utils.add_embed(it['cite'])
            elif el.find('iframe'):
                it = el.find('iframe')
                new_html = utils.add_embed(it['src'])
            elif el.find('script', attrs={"src": re.compile(r'www\.buzzsprout\.com')}):
                it = el.find('script', attrs={"src": re.compile(r'www\.buzzsprout\.com')})
                new_html = utils.add_embed(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                parent = it.find_parent('p')
                if parent:
                    parent.insert_after(new_el)
                    parent.decompose()
                else:
                    parent = el.find_parent('figure')
                    if parent:
                        parent.insert_after(new_el)
                        parent.decompose()
                if parent:
                    el.unwrap()
                    continue
            elif el.find('script', attrs={"src": re.compile(r'gist\.github\.com')}):
                it = el.find('script', attrs={"src": re.compile(r'gist\.github\.com')})
                m = re.search(r'/([a-f0-9]+)\.js', it['src'])
                if m:
                    gist_id = m.group(1)
                    gist_js = utils.get_url_html('https://gist.github.com/{}.js'.format(gist_id))
                    if gist_js:
                        m = re.search(r'https:\/\/gist\.github\.com\/([^\/]+)\/{}\/raw'.format(gist_id), gist_js)
                        if m:
                            gist_user = m.group(1)
                            gist = utils.get_url_html(m.group(0))
                            if gist:
                                new_html = '<h4>Gist: <a href="https://gist.github.com/{0}/{1}">https://gist.github.com/{0}/{1}</a></h4><pre style="margin-left:2em; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;">{2}</pre>'.format(gist_user, gist_id, html.escape(gist))
            elif el.find(id='remixd-audio-player-script'):
                el.decompose()
                continue
            elif el.find('div', class_=['outpost-pub-container', 'subscribe']):
                el.decompose()
                continue
            elif el.find('ins', class_='adsbygoogle'):
                el.decompose()
                continue
            elif el.find('path', attrs={"d": "M0 0H6V6H0V0ZM12 6H6V12H0V18H6V12H12V18H18V12H12V6ZM12 6V0H18V6H12ZM30 0H36V6H30V0ZM42 6H36V12H30V18H36V12H42V18H48V12H42V6ZM42 6V0H48V6H42ZM66 0H60V6H66V12H60V18H66V12H72V18H78V12H72V6H78V0H72V6H66V0Z"}):
                new_html = '<div>&nbsp;</div><hr style="border:8px dashed black; border-radius:4px; width:25%; margin-left:auto; margin-right:auto;"/><div>&nbsp;</div>'
            elif el.find('a', attrs={"href": re.compile(r'api\.addthis\.com')}):
                el.decompose()
                continue
            elif el.find(id='footnotes') or el.find(class_='footnotes') or el.find('a', class_='footnote-anchor'):
                el.unwrap()
                continue
            elif el.find('pre'):
                el.unwrap()
                continue

            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled kg-card in ' + item['url'])
                # print(str(el))

        item['content_html'] += str(soup)
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])

    if post_json.get('visibility') and post_json['visibility'] == 'paid':
        item['content_html'] += '<h2 style="text-align:center;"><a href="{}">This post is for paying subscribers only</a></h2>'.format(item['url'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/rss/' in args['url'] or 'feedburner.com' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    tld = tldextract.extract(args['url'])
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    sites_json = utils.read_json_file('./sites.json')
    site_json = sites_json[tld.domain]
    ghost_url = '{}posts/?key={}&limit=10&page=1&include=authors%2Ctags'.format(site_json['data-api'], site_json['data-key'])
    post_filters = site_json['post_filters'].copy()
    if 'tag' in paths:
        post_filters.append('tag:' + paths[-1])
    elif 'author' in paths:
        post_filters.append('author:' + paths[-1])
    if post_filters:
        ghost_url += '&filter=' + quote_plus('+'.join(post_filters))
    print(ghost_url)
    ghost_json = utils.get_url_json(ghost_url)
    if not ghost_json:
        return None
    if save_debug:
        utils.write_file(ghost_json, './debug/feed.json')

    n = 0
    feed_items = []
    for post in ghost_json['posts']:
        if save_debug:
            logger.debug('getting content for ' + post['url'])
        item = get_item(post, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed