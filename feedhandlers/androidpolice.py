import html, json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if split_url.query:
        query = re.sub(r'w=\d+', 'w={}'.format(width), split_url.query)
        query = re.sub(r'(\?|&)h=\d+', '', query)
    else:
        query = 'w={}'.format(width)
    return '{}://{}{}?{}'.format(split_url.scheme, split_url.netloc, split_url.path, query)


def add_figure(el_figure):
    it = el_figure.find('source')
    if it:
        img_src = it.get('srcset')
        if not img_src:
            img_src = it.get('data-srcset')
            if not img_src:
                return '<h4>unknown img src</h4>'
    if el_figure.figcaption:
        caption = el_figure.figcaption.get_text()
    else:
        caption = ''
    return add_image(img_src, caption)


def add_image(img_src, caption):
    w,h = utils.get_image_size(img_src)
    #print(w,h)
    if w and h and h > w:
        return utils.add_image(resize_image(img_src, width=w), caption, fig_style="width:50%; margin-left:auto; margin-right:auto;")
    return utils.add_image(resize_image(img_src), caption)


def get_content(url, args, save_debug=False):
    # Some content is blocked without this header
    article_html = utils.get_url_html(url)
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    # article_html = re.sub(r'::(after|before|marker)\b', '', article_html)
    soup = BeautifulSoup(article_html, 'html.parser')

    ld_article = None
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string.replace('\n', ''))
        if ld_json['@type'] == 'Article':
            ld_article = ld_json
            break

    m = re.search(r'VALNET_GLOBAL_POSTID = "(\d+)"', article_html)
    if m:
        post_id = m.group(1)
    else:
        post_id = url

    item = {}
    item['id'] = post_id
    item['url'] = url

    if ld_article:
        if save_debug:
            utils.write_file(ld_article, './debug/debug.json')

        item['title'] = html.unescape(ld_article['headline'])

        dt = datetime.fromisoformat(ld_article['datePublished'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        dt_mod = datetime.fromisoformat(ld_article['dateModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt_mod.isoformat()

        author = ''
        if ld_article.get('author'):
            if isinstance(ld_article['author'], dict):
                author = ld_article['author']['name']
            elif isinstance(ld_article['author'], list):
                authors = []
                for author in ld_article['author']:
                    authors.append(author['name'])
                author = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        else:
            el = soup.find('a', class_='author')
            if el:
                author = el.get_text().replace('By ', '')
        if author:
            item['author'] = {"name": author}

        item['tags'] = ld_article['keywords'].copy()
        item['_image'] = ld_article['image']['url']

        item['summary'] = ld_article['description']
    else:
        el = soup.find('meta', attrs={"property": "og:title"})
        if el:
            item['title'] = html.unescape(el['content'])

        el = soup.find('meta', attrs={"property": "article:published_time"})
        if el:
            dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        el = soup.find('meta', attrs={"property": "article:modified_time"})
        if el:
            dt_mod = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
            item['date_modified'] = dt_mod.isoformat()

        el = soup.find('meta', attrs={"property": "article:modified_time"})
        if el:
            dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
            item['date_modified'] = dt.isoformat()

        el = soup.find('a', class_='author')
        if el:
            item['author'] = {}
            item['author']['name'] = el.get_text().replace('By ', '')

        el = soup.find(class_='article-tags')
        if el:
            item['tags'] = []
            for it in el.find_all('li'):
                item['tags'].append(it.get_text())

        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

        el = soup.find('meta', attrs={"name": "description"})
        if el:
            item['summary'] = el['content']

    item['content_html'] = ''
    if item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    el = soup.find(class_='heading_image')
    if el:
        item['content_html'] += add_figure(el.figure)

    article_body = soup.find(class_='article-body')
    if article_body:
        el = article_body.find(id='article-waypoint')
        if el:
            for it in el.find_next_siblings():
                it.decompose()
            el.decompose()

        el = article_body.find(class_='bottom')
        if el:
            for it in el.find_next_siblings():
                it.decompose()
            el.decompose()

        for el in article_body.find_all(class_='w-review-item'):
            for it in el.find_all(
                    class_=re.compile(r'badge|desc-more-btn|rai?ting-comments|rai?ting-stars|review-item-cta-btn')):
                it.decompose()
            it = el.find(class_='review-item-award')
            if it:
                it.name = 'span'
                it['style'] = 'color:white; background-color:red; padding:0.2em; font-size:2em;'
            it = el.find(class_='review-item-title')
            if it:
                it.name = 'h2'
            it = el.find(class_=re.compile(r'review-item-rai?ting'))
            if it:
                it['style'] = 'font-size:1.5em; font-weight:bold;'
            it = el.find(class_='w-review-item-img')
            if it:
                for img in it.find_all(class_='review-item-gallery-thumbnail'):
                    src = img.find('source')
                    new_html = add_image(resize_image(src['data-srcset']), '&nbsp;')
                    it.insert_before(BeautifulSoup(new_html, 'html.parser'))
                it.decompose()
            it = el.find(class_='item-buy')
            if it:
                new_html = '<ul>'
                for a in it.find_all(class_='item-buy-btn'):
                    new_html += '<li><a href="{}">{}</a>'.format(utils.get_redirect_url(a['href']),
                                                                 a.get_text().strip())
                new_html += '</ul>'
                it.insert_after(BeautifulSoup(new_html, 'html.parser'))
                it.decompose()

        for el in article_body.find_all(class_=re.compile(r'\bad\b')):
            el.decompose()

        for el in article_body.find_all(class_='body-img'):
            new_html = add_figure(el.figure)
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

        for el in article_body.find_all(class_='img-article-item'):
            new_html = add_figure(el.figure)
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

        for el in article_body.find_all(class_='article__gallery'):
            new_html = ''
            it = el.find(class_='gallery__section-title')
            if it:
                new_html += '<h3>{}</h3>'.format(it.get_text())
            for it in el.find_all(class_='gallery__images__item'):
                if it.figcaption:
                    caption = it.figcaption.get_text()
                else:
                    caption = ''
                new_html += add_image(resize_image(it['data-img-url']), caption)
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

        for el in article_body.find_all('img'):
            if el.parent.name != 'figure':
                new_html = ''
                if el.get('src'):
                    new_html = add_image(resize_image(el['src']))
                elif el.get('data-img-url'):
                    new_html = add_image(resize_image(el['data-img-url']))
                if new_html:
                    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                    el.decompose()
                else:
                    logger.warning('unable to determine img src in ' + url)

        for el in article_body.find_all(class_='gallery-lightbox'):
            el.decompose()

        for el in article_body.find_all(class_='w-twitter'):
            tweet_url = ''
            it = el.find(class_='twitter-tweet')
            if it:
                tweet_url = utils.get_twitter_url(it['id'])
            else:
                if el.get('id') and re.search('^\d+$', el['id']):
                    tweet_url = utils.get_twitter_url(el['id'])
            if tweet_url:
                new_html = utils.add_embed(tweet_url)
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()
            else:
                logger.warning('unhandled tweet in ' + url)

        for el in article_body.find_all(class_='w-youtube'):
            new_html = utils.add_embed('https://www.youtube.com/watch?v=' + el['id'])
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

        for el in article_body.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            if el.parent and el.parent.name == 'div':
                el.parent.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.parent.decompose()
            else:
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()

        for el in article_body.find_all(class_='w-play_store_app'):
            m = re.search(r'window\.arrayOfEmbeds\["{}"\] = {{\'play_store_app\' : \'(.+?)\'}};\n'.format(el['id']), article_html)
            if m:
                new_html = html.unescape(m.group(1))
                new_html = new_html[1:-1].replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()

        for el in article_body.find_all(class_='app-widget-container'):
            desc = ''
            link = ''
            name = ''
            it = el.find('a', class_='app-widget-name')
            if it:
                link = it['href']
                name = it.get_text()
            else:
                it = el.find(class_='app-widget-details')
                if it and it.a:
                    link = it.a['href']
                    name = it.a.get_text()
            if link:
                desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4>'.format(link, name)
            elif name:
                desc = '<h4 style="margin-top:0; margin-bottom:0.5em;">{}</h4>'.format(name)
            link = ''
            name = ''
            it = el.find('a', class_=re.compile(r'app-widget-developp?er'))
            if it:
                link = it['href']
                name = it.get_text()
            else:
                it = el.find(class_='app-developer-name')
                if it:
                    if it.a:
                        link = it.a['href']
                    name = it.get_text()
            if link:
                desc += '<small>Developer: <a href="{}">{}</a>'.format(link, name)
            elif name:
                desc += '<small>Developer: {}'.format(name)
            else:
                m = re.search(r'>(Developer: [^<]+)<', str(el))
                if m:
                    desc += '<small>{}'.format(m.group(1))
                else:
                    desc += '<small>Developer: N/A'
            it = el.find(class_='app-widget-price')
            if it:
                desc += '<br/>{}'.format(it.get_text())
            else:
                desc += '<br/>Price: N/A'
            it = el.find(class_=re.compile(r'app-widget-rating'))
            if it:
                desc += '<br/>Rating: {}</small>'.format(it.get_text())
            else:
                desc += '<br/>Rating: N/A</small>'

            poster = ''
            it = el.find('img')
            if it:
                poster = '{}/image?url={}&width=128&height=128'.format(config.server, quote_plus(it['src']))
            else:
                it = el.find(id=True)
                if it:
                    script = article_body.find('script', string=re.compile(r'window\.arrayOfEmbeds\["{}"\]'.format(it['id'])))
                    if script:
                        m = re.search(r'<img src="([^"\']+)"', html.unescape(script.string), flags=re.S)
                        if m:
                            poster = '{}/image?url={}&width=128&height=128'.format(config.server, quote_plus(m.group(1)))
            if not poster:
                poster = '{}/image?width=128&height=128'.format(config.server)
            #new_html = '<div><a href="{}"><img style="height:128px; float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;"></div>'.format(
            new_html = '<table><tr><td style="width:128px;"><a href="{}"><img style="height:128px;" src="{}"/></a></td><td style="vertical-align:top;">{}</td></tr></table>'.format(link, poster, desc)
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

        for el in article_body.find_all(class_='emaki-custom-block'):
            if 'emaki-custom-update' in el['class']:
                for it in el.find_all(class_='update'):
                    it.name = 'blockquote'
                    it.attrs.clear()
                    it['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
                article_body.insert(0, el)
                el.unwrap()
                if dt_mod:
                    item['_timestamp'] = dt_mod.timestamp()
            elif 'emaki-custom-tip' in el['class']:
                for it in el.find_all(class_='tip'):
                    it.name = 'blockquote'
                    it.insert(0, BeautifulSoup('<h4>Tip:</h4>', 'html.parser'))
                    it.attrs.clear()
                    it['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
                el.unwrap()

        for el in article_body.find_all('blockquote'):
            it = el.find(class_='pullquote')
            if it:
                quote = ''
                for p in it.find_all('p'):
                    if quote:
                        quote += '<br/><br/>'
                    quote += re.sub(r'^<[^>]+>|<\/[^>]+>$', '', str(p).strip()).strip()
                new_html = utils.add_pullquote(quote)
            else:
                new_html = utils.add_blockquote(utils.bs_get_inner_html(el))
            if new_html:
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()

        for el in article_body.find_all(class_='article-jumplink'):
            it = el.find(class_='jumplink-title')
            if it and re.search(r'update', it.get_text(), flags=re.I):
                el.decompose()

        for el in article_body.find_all(class_=re.compile(r'affiliate')):
            if el.a:
                el.a['href'] = utils.get_redirect_url(el.a['href'])

        for el in article_body.find_all(class_='affiliate-single'):
            el.name = 'ul'
            el.attrs = {}
            for it in el.find_all('a'):
                it.wrap(soup.new_tag('li'))

        for el in article_body.find_all('button', class_='article-info-table-btn'):
            el.decompose()

        for el in article_body.find_all('script'):
            el.decompose()

        # Remove comment sections
        for el in article_body.find_all(text=lambda text: isinstance(text, Comment)):
            el.extract()

        item['content_html'] += re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', article_body.decode_contents())
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
