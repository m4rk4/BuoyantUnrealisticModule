import av, bs4, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    #print(img_src)
    split_url = urlsplit(img_src)
    query = parse_qs(split_url.query)
    if query.get('url'):
        #print(query)
        return img_src
    if query.get('w') or query.get('h') or query.get('fit'):
        return '{}://{}{}?w={}&ssl=1'.format(split_url.scheme, split_url.netloc, split_url.path, width)
    if query.get('width') or query.get('height'):
        return '{}://{}{}?width={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)
    return img_src


def add_image(el, el_parent, base_url, caption=True, decompose=True, gallery=False, n=0):
    #print(el)
    if el.name == None:
        return

    if el.name == 'img':
        img = el
    else:
        img = el.find('img')
        if not img:
            img = el.find('amp-img')
            if not img:
                img = el.find('source')
    if not img:
        logger.warning('image block without img')
        return

    it = img.find_parent('a')
    if it and it.get('href'):
        link = it['href']
    else:
        link = ''

    if not el_parent:
        el_parent = el
        for it in reversed(el.find_parents()):
            #print('Parent: ' + it.name)
            if it.name == 'p':
                has_str = False
                for c in it.contents:
                    if isinstance(c, bs4.element.NavigableString) or (isinstance(c, bs4.element.Tag) and c.name in ['b', 'em', 'i', 'strong']):
                        has_str = True
                if not has_str:
                    el_parent = it
                    break
            elif not it.find('p'):
                el_parent = it
                break
        # if el.parent and el.parent.name == 'a' and el.parent.get('href'):
        #     el_parent = el.parent
        # if el_parent.parent and (el_parent.parent.name == 'center' or el_parent.parent.name == 'figure'):
        #     el_parent = el_parent.parent
        # if el_parent.parent and re.search(r'^(div|h\d|p)$', el_parent.parent.name):
        #     el_parent = el_parent.parent

    if link and img.get('class') and 'attachment-thumbnail' in img['class']:
        img_src = link
        link = ''
    elif img.get('data-lazy-srcset') and not img['data-lazy-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-lazy-srcset'], 1000)
    elif img.get('data-lazy-load-srcset') and not img['data-lazy-load-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-lazy-load-srcset'], 1000)
    elif img.get('data-srcset') and not img['data-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-srcset'], 1000)
    elif img.get('srcset') and not img['srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['srcset'], 1000)
    elif img.get('data-lazy-src') and not img['data-lazy-src'].startswith('data:image/gif;base64'):
        img_src = img['data-lazy-src']
    elif img.get('data-lazy-load-src') and not img['data-lazy-load-src'].startswith('data:image/gif;base64'):
        img_src = img['data-lazy-load-src']
    elif img.get('data-dt-lazy-src') and not img['data-dt-lazy-src'].startswith('data:image/gif;base64'):
        img_src = img['data-dt-lazy-src']
    elif img.get('data-src') and not img['data-src'].startswith('data:image/gif;base64'):
        img_src = img['data-src']
    else:
        img_src = img['src']

    if img_src.startswith('//'):
        img_src = 'https:' + img_src
    elif img_src.startswith('/'):
        img_src = base_url + img_src

    if re.search(r'abyssalchronicles.*thumb_', img_src):
        img_src = img_src.replace('thumb_', 'normal_')

    captions = []
    if el_parent.get('class') and 'multiple-images' in el_parent['class']:
        cap = '({})'.format(n)
        if caption:
            it = el_parent.find(class_='multiple-images__caption')
            if it:
                captions.append(cap + '<br/><br/>' + it.decode_contents())
        else:
            captions.append(cap)
    if caption:
        if el.get('class') and 'bp-embedded-image' in el['class']:
            for it in el.find_all('em'):
                captions.append(it.get_text())
        else:
            if gallery:
                elm = el
            else:
                elm = el_parent

            credit = ''
            it = elm.find(class_='credit')
            if it and it.get_text().strip():
                credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='imageCredit')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_=re.compile(r'image-attribution|image-credit|credits-text|image_source'))
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='slide-caption')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='slide-credit')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='visual-by')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='author-name')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if it:
                it.decompose()

            it = elm.find(class_='caption')
            if it and it.get_text().strip():
                captions.insert(0, it.get_text().strip())
            if not captions:
                it = elm.find(class_=re.compile(r'wp-block-media-text__content'))
                if it and it.get_text().strip():
                    captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', it.decode_contents().strip()))
            if not captions:
                it = elm.find(class_=re.compile(r'caption-text|image-caption'))
                if it and it.get_text().strip():
                    captions.append(it.get_text())
            if not captions:
                it = elm.find(class_=re.compile(r'text'))
                if it and it.get_text().strip():
                    captions.append(it.get_text())
            if not captions:
                it = elm.find(class_='undark-caption')
                if it and it.get_text().strip():
                    captions.append(it.decode_contents().replace('<p>', '').replace('</p>', ' ').strip())
            if not captions:
                it = elm.find(class_='singleImageCaption')
                if it and it.get_text().strip():
                    i = it.find('i', class_='fas')
                    if i:
                        i.decompose()
                    captions.append(it.decode_contents())
            if not captions:
                it = elm.find('figcaption')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())

            if credit:
                captions.append(credit)

            if not captions:
                if img.get('data-image-caption'):
                    captions.append(img['data-image-caption'])
                elif img.get('data-image-title') and not re.search(r'\w(_|-)\w||\w\d+$', img['data-image-title']):
                    captions.append(img['data-image-title'])

    desc = ''
    if el.find(class_='picture-desc'):
        it = el.find(class_='gallery-heading')
        if it and it.get_text().strip():
            desc += '<h3>{}</h3>'.format(it.get_text().strip())
        it = el.find(class_='gallery-content')
        if it and it.get_text().strip():
            it.attrs = {}
            it.name = 'p'
            desc += str(it)

    if not (el.get('class') and 'bannerad' in el['class']):
        new_html = utils.add_image(resize_image(img_src), ' | '.join(captions), link=link, desc=desc)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el_parent.insert_before(new_el)

    if decompose:
        if len(el_parent.find_all('img')) > 1:
            el.decompose()
        else:
            el_parent.decompose()
    return new_html


def render_content(content, url):
    content_html = ''
    for block in content:
        if isinstance(block, str):
            content_html += block

        elif isinstance(block, dict):
            if block.get('tag'):
                if block['tag'] == 'a':
                    content_html += '<a href="{}">{}</a>'.format(block['attributes']['href'], render_content(block['content'], url))
                elif block['tag'] == 'caption':
                    image = next((it for it in block['content'] if it['tag'] == 'img'), None)
                    if image:
                        captions = []
                        caption = next((it for it in block['content'] if isinstance(it, dict) and it['tag'] == 'figcaption'), None)
                        if caption and caption.get('content'):
                            captions.append(render_content(caption['content'], url))
                        caption = next((it for it in block['content'] if isinstance(it, dict) and it['tag'] == 'figcredit'), None)
                        if caption and caption.get('content'):
                            captions.append(render_content(caption['content'], url))
                        content_html += utils.add_image(image['attributes']['src'], ' | '.join(captions))
                    else:
                        logger.warning('unhandled caption tag')
                elif block['tag'] == 'video':
                    if 'time.com' in url and block['attributes'].get('videoid'):
                        content_html += utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(block['attributes']['videoid']))
                else:
                    #print(block['tag'])
                    content_html += '<{0}>{1}</{0}>'.format(block['tag'],render_content(block['content'], url))
            else:
                logger.warning('unhandled dict block without tag')

        else:
            logger.warning('unhandled block type {}'.format(type(block)))

    return content_html


def get_post_content(post, args, site_json, save_debug=False):
    if save_debug:
        utils.write_file(post, './debug/debug.json')

    yoast_json = None
    if post.get('yoast_head_json') and post['yoast_head_json'].get('schema'):
        yoast_json = post['yoast_head_json']['schema']
    elif post.get('yoast_head'):
        soup = BeautifulSoup(post['yoast_head'], 'html.parser')
        el = soup.find('script', class_='yoast-schema-graph')
        if el:
            yoast_json = json.loads(el.string)

    item = {}
    item['id'] = post['guid']['rendered']
    item['url'] = post['link']
    item['title'] = BeautifulSoup('<p>{}</p>'.format(post['title']['rendered']), 'html.parser').get_text()

    dt = datetime.fromisoformat(post['date_gmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post['modified_gmt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    item['author'] = {}
    authors = []
    if post['_links'].get('author') and 'skip_wp_user' not in args:
        for link in post['_links']['author']:
            link_json = utils.get_url_json(link['href'])
            if link_json:
                if link_json.get('name') and not re.search(r'No Author', link_json['name'], flags=re.I):
                    authors.append(link_json['name'])
    if not authors and yoast_json:
        for it in yoast_json['@graph']:
            if it['@type'] == 'Article' and it.get('author'):
                if isinstance(it['author'], list):
                    for author in it['author']:
                        if author.get('name'):
                            authors.append(author['name'])
                elif isinstance(it['author'], dict) and it['author'].get('name'):
                    authors.append(it['author']['name'])
                elif isinstance(it['author'], str):
                    authors.append(it['author'])
        if not authors:
            for it in yoast_json['@graph']:
                if it['@type'] == 'Person':
                    if it.get('name') and not re.search(r'No Author', it['name'], flags=re.I):
                        authors.append(it['name'])
    if not authors and post.get('parsely') and post['parsely'].get('meta'):
        if post['parsely']['meta'].get('author'):
            for author in post['parsely']['meta']['author']:
                authors.append(author['name'])
        elif post['parsely']['meta'].get('creator'):
            authors = post['parsely']['meta']['creator'].copy()
    if not authors and post.get('parselyMeta') and post['parselyMeta'].get('parsely-author'):
        for it in post['parselyMeta']['parsely-author']:
            authors.append(it)
    if not authors and post.get('authors'):
        for it in post['authors']:
            if isinstance(it, dict):
                if it.get('display_name'):
                    authors.append(it['display_name'])
                elif it.get('name'):
                    authors.append(it['name'])
    if not authors and post.get('meta') and post['meta'].get('byline'):
        authors.append(post['meta']['byline'])
    if not authors and post['_links'].get('ns:byline'):
        for link in post['_links']['ns:byline']:
            link_json = utils.get_url_json(link['href'])
            if link_json:
                if link_json.get('title'):
                    authors.append(link_json['title']['rendered'])
    if not authors and post['_links'].get('author') and 'skip_wp_user' in args:
        update_sites = False
        wp_item = None
        for i, link in enumerate(post['_links']['author']):
            author = list(filter(None, urlsplit(link['href']).path[1:].split('/')))[-1]
            if site_json.get('authors') and site_json['authors'].get(author):
                authors.append(site_json['authors'][author])
            elif site_json.get('authors') and site_json['authors'].get('default'):
                authors.append(site_json['authors']['default'])
            else:
                if not wp_item:
                    embed_args = args.copy()
                    embed_args['embed'] = True
                    wp_item = wp.get_content(item['url'], embed_args, site_json, False)
                if wp_item and wp_item.get('author'):
                    wp_authors = re.split(r'(, | and )', wp_item['author']['name'])
                    authors.append(wp_authors[i])
                    if site_json.get('authors'):
                        site_json['authors'][author] = wp_authors[i]
                        logger.debug('adding unknown author {} as {}'.format(author, wp_authors[i]))
                        update_sites = True
                else:
                    logger.debug('unknown author {} in {}'.format(author, item['url']))
                    authors.append('Unknown author {}'.format(author))
        if update_sites:
            utils.update_sites(item['url'], site_json)
    if authors:
        for i in range(len(authors)):
            authors[i] = re.sub(r', (.*)', r' (\1)', authors[i])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        if 'author' in args:
            embed_args = args.copy()
            embed_args['embed'] = True
            wp_item = wp.get_content(item['url'], embed_args, site_json, False)
            if wp_item and wp_item.get('author'):
                item['author']['name'] = wp_item['author']['name']
        else:
            item['author']['name'] = urlsplit(item['url']).netloc

    item['tags'] = []
    if not 'skip_wp_terms' in args:
        if 'wp:term' in post['_links']:
            for link in post['_links']['wp:term']:
                if link.get('taxonomy') and link['taxonomy'] != 'author' and link['taxonomy'] != 'site-layouts':
                    link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            if it.get('name'):
                                item['tags'].append(it['name'])
    if yoast_json:
        it = next((it for it in yoast_json['@graph'] if it.get('keywords')), None)
        if it:
            for tag in it['keywords']:
                if tag.startswith('category-'):
                    item['tags'] += tag.split('/')[1:]
                else:
                    item['tags'].append(tag)
    if post.get('parsely') and post['parsely'].get('meta') and post['parsely']['meta'].get('keywords'):
        item['tags'] = post['parsely']['meta']['keywords'].copy()
    elif post.get('parselyMeta') and post['parselyMeta'].get('parsely-tags'):
        item['tags'] = post['parselyMeta']['parsely-tags'].split(',')
    if item.get('tags'):
        # Remove duplicate tags - case insensitive
        # https://stackoverflow.com/questions/24983172/how-to-eliminate-duplicate-list-entries-in-python-while-preserving-case-sensitiv
        wordset = set(item['tags'])
        item['tags'] = [it for it in wordset if it.istitle() or it.title() not in wordset]
    else:
        del item['tags']

    caption = ''
    if 'skip_wp_media' not in args:
        if post['_links'].get('wp:featuredmedia'):
            for link in post['_links']['wp:featuredmedia']:
                link_json = utils.get_url_json(link['href'])
                if link_json:
                    if link_json['media_type'] == 'image':
                        item['_image'] = link_json['source_url']
                        captions = []
                        if link_json.get('description'):
                            soup = BeautifulSoup(link_json['description']['rendered'], 'html.parser')
                            if not soup.find(class_=True):
                                caption = soup.get_text().strip()
                                if caption:
                                    captions.append(caption)
                        if not captions and link_json.get('caption'):
                            soup = BeautifulSoup(link_json['caption']['rendered'], 'html.parser')
                            if not soup.find(class_=True):
                                #caption = soup.get_text().strip()
                                caption = re.sub(r'^<p>(.*?)</p>$', r'\1', link_json['caption']['rendered'])
                                if caption:
                                    captions.append(caption)
                        if not captions and link_json.get('title'):
                            soup = BeautifulSoup(link_json['title']['rendered'], 'html.parser')
                            if not soup.find(class_=True):
                                caption = soup.get_text().strip()
                                if caption and not re.search(r'\w(_|-)\w||\w\d+$', caption):
                                    captions.append(caption)
                        caption = ' | '.join(captions)
        if not item.get('_image') and post['_links'].get('wp:attachment'):
            for link in post['_links']['wp:attachment']:
                if not item.get('_image'):
                    link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            if it['media_type'] == 'image':
                                item['_image'] = it['source_url']
                                captions = []
                                if it.get('description'):
                                    soup = BeautifulSoup(it['description']['rendered'], 'html.parser')
                                    if not soup.find(class_=True):
                                        caption = soup.get_text().strip()
                                        if caption:
                                            captions.append(caption)
                                if not captions and it.get('caption'):
                                    soup = BeautifulSoup(it['caption']['rendered'], 'html.parser')
                                    if not soup.find(class_=True):
                                        #caption = soup.get_text().strip()
                                        caption = re.sub(r'^<p>(.*?)</p>$', r'\1', it['caption']['rendered'])
                                        if caption:
                                            captions.append(caption)
                                if not captions and it.get('title'):
                                    soup = BeautifulSoup(it['title']['rendered'], 'html.parser')
                                    if not soup.find(class_=True):
                                        caption = soup.get_text().strip()
                                        if caption and not re.search(r'\w(_|-)\w|\w\d+$', caption):
                                            captions.append(caption)
                                caption = ' | '.join(captions)
                                break
    if yoast_json:
        it = next((it for it in yoast_json['@graph'] if (it.get('@type') and it['@type'] == '@ImageObject')), None)
        if it:
            if it.get('contentUrl'):
                item['_image'] = it['contentUrl']
            elif it.get('url'):
                item['_image'] = it['url']
            if it.get('caption'):
                caption = it['caption']
    if not item.get('_image'):
        if post.get('yoast_head_json') and post['yoast_head_json'].get('og_image'):
            item['_image'] = post['yoast_head_json']['og_image'][0]['url']
        elif post.get('jetpack_featured_media_url'):
            item['_image'] = post['jetpack_featured_media_url']
        elif post.get('parselyMeta') and post['parselyMeta'].get('parsely-image-url'):
            item['_image'] = post['parselyMeta']['parsely-image-url']
        elif post.get('episode_featured_image'):
            item['_image'] = post['episode_featured_image']
        elif post.get('acf'):
            if post['acf'].get('hero') and post['acf']['hero'].get('image'):
                item['_image'] = post['acf']['hero']['image']
            elif post['acf'].get('post_hero') and post['acf']['post_hero'].get('image'):
                item['_image'] = post['acf']['post_hero']['image']

    if post.get('excerpt') and post['excerpt'].get('rendered'):
        item['summary'] = BeautifulSoup(post['excerpt']['rendered'], 'html.parser').get_text()
    elif post.get('yoast_head_json'):
        if post['yoast_head_json'].get('description'):
            item['summary'] = post['yoast_head_json']['description']
        elif post['yoast_head_json'].get('og_description'):
            item['summary'] = post['yoast_head_json']['og_description']
    if not item.get('summary') and yoast_json:
        it = next((it for it in yoast_json['@graph'] if it.get('description')), None)
        if it:
            item['summary'] = it['description']

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;"><a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a><div style="margin-left:8px; margin-right:8px;"><h4><a href="{}">{}</a></h4><p><small>{}</small></p></div></div>'.format(item['url'], item['_image'], item['url'], item['title'], item['summary'])
        return item

    content_html = ''
    # if post.get('content') and post['content'].get('structured'):
    #     logger.debug('getting structured content...')
    #     item['content_html'] = content_html + render_content(post['content']['structured'], item['url'])
    #     return item
    if post.get('content') and post['content'].get('rendered'):
        content_html += post['content']['rendered']
        utils.write_file(content_html, './debug/debug.html')
    elif post.get('acf'):
        for module in post['acf']['article_modules']:
            if module['acf_fc_layout'] == 'text_block':
                content_html += module['copy']
            elif module['acf_fc_layout'] == 'list_module':
                content_html += '<h3>{}</h3>'.format(module['title'])
                if module['list_type'] == 'video':
                    if 'youtube' in module['video_url']:
                        for yt in re.findall(r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})', module['video_url']):
                            content_html += utils.add_youtube(yt)
                    else:
                        logger.warning('unhandled video_url in ' + item['url'])
                else:
                    logger.warning('unhandled list_type {} in {}'.format(module['list_type'], item['url']))
                content_html += module['copy']
            elif module['acf_fc_layout'] == 'image_block':
                content_html += utils.add_image(module['image'], module['caption'])
            elif module['acf_fc_layout'] == 'affiliates_block' or module['acf_fc_layout'] == 'inline_recirculation' or module['acf_fc_layout'] == 'membership_block':
                pass
            else:
                logger.warning('unhandled acf_fc_layout module {} in {}'.format(module['acf_fc_layout'], item['url']))
    else:
        logger.warning('unknown post content in {}' + item['url'])

    content_html = content_html.replace('\u2028', '')

    lede = ''
    subtitle = ''
    if post.get('subtitle'):
        subtitle = post['subtitle']
    elif post.get('rayos_subtitle'):
        subtitle = post['rayos_subtitle']
    elif post.get('meta'):
        if post['meta'].get('sub_heading'):
            lede += '<p><em>{}</em></p>'.format(post['meta']['sub_heading'])
        elif post['meta'].get('multi_title'):
            multi_title = json.loads(post['meta']['multi_title'])
            if multi_title['titles']['headline'].get('additional') and multi_title['titles']['headline']['additional'].get('headline_subheadline'):
                lede += '<p><em>{}</em></p>'.format(multi_title['titles']['headline']['additional']['headline_subheadline'])
    if not subtitle and 'add_subtitle' in args:
        if post.get('yoast_head_json'):
            if post['yoast_head_json'].get('description'):
                lede += '<p><em>{}</em></p>'.format(post['yoast_head_json']['description'])
            elif post['yoast_head_json'].get('og_description'):
                lede += '<p><em>{}</em></p>'.format(post['yoast_head_json']['og_description'])
        elif post.get('excerpt') and post['excerpt'].get('rendered'):
            lede += '<p><em>{}</em></p>'.format(BeautifulSoup(post['excerpt']['rendered'], 'html.parser').get_text())
    if subtitle:
        lede += '<p><em>{}</em></p>'.format(subtitle)

    if 'skip_lede_img' not in args:
        if item.get('_image'):
            # Add lede image if it's not in the content or if add_lede_img arg
            if not re.search(urlsplit(item['_image']).path, content_html, flags=re.I) or 'add_lede_img' in args:
                lede += utils.add_image(item['_image'], caption)
        if post.get('meta') and post['meta'].get('_pmc_featured_video_override_data'):
            lede += utils.add_embed(post['meta']['_pmc_featured_video_override_data'])

    if post.get('acf') and post['acf'].get('post_hero') and post['acf']['post_hero'].get('number_one_duration'):
        # https://www.stereogum.com/2211784/the-number-ones-chamillionaires-ridin-feat-krayzie-bone/columns/the-number-ones/
        lede += '<div style="font-size:1.1em; font-weight:bold; text-align:center;">{}<br/>Weeks at #1: {}<br/>Rating: {}</div>'.format(post['acf']['post_hero']['chart_date'], post['acf']['post_hero']['number_one_duration'], post['acf']['post_hero']['rating'])

    if 'bigthink.com' in item['url']:
        page_html = utils.get_url_html(item['url'])
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            ld_json = None
            for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
                ld_json = json.loads(el.string)
                if ld_json['@type'] == 'Article':
                    break
                ld_json = None
            if ld_json:
                item['author']['name'] = ld_json['author']['name']
            el = soup.find('div', string=re.compile(r'Key Takeaways'))
            if el:
                it = el.parent.find('ul')
                if it:
                    lede += '<h3>Key Takeaways</h3>' + str(it) + '<hr/>'
    elif 'toucharcade.com' in item['url'] and 'Reviews' in item['tags']:
        rating = list(filter(re.compile(r'[\d\.]+ star').match, item['tags']))
        if rating:
            lede += '<div style="font-size:2em; font-weight:bold; text-align:center">TA rating: {}</div>'.format(rating[0])

    # Review summary
    if post.get('wppr_data') and post['wppr_data'].get('_wppr_review_template'):
        lede += '<div style="text-align:center;"><h2>{}</h2>'.format(post['wppr_data']['cwp_rev_product_name'])
        lede += '<h3><span style="font-size:2em;">{:.1f}</span>/10</h3>'.format(float(post['wppr_data']['wppr_rating'])/10)
        if 'techaeris.com' in item['url']:
            lede += '<img src="https://techaeris.com/wp-content/uploads/2017/03/TA-ratings-{:.0f}.png"/>'.format(float(post['wppr_data']['wppr_rating']))
            soup = BeautifulSoup(post['content']['rendered'], 'html.parser')
            el = soup.find('img', attrs={"src": re.compile(r'EDITORS-CHOICE|HIGHLY-RATED|TOP-PICK')})
            if el:
                lede += '<img src="{}"/>'.format(el['src'])
                el.find_parent('div', class_='wp-block-image').decompose()
            el = soup.find('img', attrs={"src": re.compile(r'TA-ratings-\d+.png')})
            if el:
                el.find_parent('div', class_='wp-block-image').decompose()
            post['content']['rendered'] = str(soup)
        lede += '</div>'
        if post['wppr_data'].get('wppr_options'):
            lede += '<h3>Scores</h3><table style="margin-left:1.5em;">'
            for key, val in post['wppr_data']['wppr_options'].items():
                lede += '<tr><td>{}</td><td>{:.1f}</td></tr>'.format(val['name'], float(val['value'])/10)
            lede += '</table>'
        if post['wppr_data'].get('wppr_pros'):
            lede += '<h3>Pros</h3><ul>'
            for it in post['wppr_data']['wppr_pros']:
                if it:
                    lede += '<li>{}</li>'.format(it)
            lede += '</ul>'
        if post['wppr_data'].get('wppr_cons'):
            lede += '<h3>Cons</h3><ul>'
            for it in post['wppr_data']['wppr_cons']:
                if it:
                    lede += '<li>{}</li>'.format(it)
            lede += '</ul>'
        if post['wppr_data'].get('wppr_links'):
            if post['wppr_data'].get('cwp_rev_price'):
                lede += '<h3>Buy: {}</h3><ul>'.format(post['wppr_data']['cwp_rev_price'])
            else:
                lede += '<h3>View</h3><ul>'
            for key, val in post['wppr_data']['wppr_links'].items():
                lede += '<li><a href="{}">{}</a></li>'.format(val, key)
            lede += '</ul>'

    if re.search('makezine\.com/(projects|products)', item['url']):
        page_html = utils.get_url_html(item['url'])
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            if '/projects/' in item['url']:
                lede += '<h2><u>Project Steps</u></h2>'
                for el in soup.find_all(class_='project-step'):
                    it = el.find(class_='step-buttons')
                    if it:
                        it.decompose()
                    lede += el.decode_contents()
            elif '/products/' in item['url']:
                soup = BeautifulSoup(page_html, 'lxml')
                el = soup.find(class_='why-buy')
                if el:
                    if el.h4:
                        el.h4.decompose()
                    lede += '<h2>Why Buy?</h2>' + el.decode_contents()
                el = soup.find('table', id='specs')
                if el:
                    el.attrs = {}
                    it = el.find('tr', class_='table-title')
                    if it:
                        it.decompose()
                    lede += '<h2>Specs</h2>' + str(el)

    item['content_html'] = format_content(lede + content_html, item, site_json)

    # if re.search('makezine\.com/(projects|products)', item['url']):
    #     page_html = utils.get_url_html(item['url'])
    #     utils.write_file(page_html, './debug/debug.html')
    #     if page_html:
    #         if '/projects/' in item['url']:
    #             item['content_html'] += '<h2><u>Project Steps</u></h2>'
    #             soup = BeautifulSoup(page_html, 'lxml')
    #             for el in soup.find_all(class_='project-step'):
    #                 item['content_html'] += el.decode_contents()
    #             ld_json = []
    #             for m in re.findall(r'<script[^>]+type=\"application/ld\+json\">(.*?)</script>', page_html, flags=re.S):
    #                 ld_json.append(json.loads(m))
    #             if ld_json:
    #                 ld = next((it for it in ld_json if it.get('@type') == 'HowTo'), None)
    #                 if ld:
    #                     item['content_html'] += '<h2><u>Project Steps</u></h2>'
    #                     for i, step in enumerate(ld['step']):
    #                         if re.search('^\d', step['name']):
    #                             item['content_html'] += '<h2>{}</h2>'.format(step['name'])
    #                         else:
    #                             item['content_html'] += '<h2>{}. {}</h2>'.format(i+1, step['name'])
    #                         if step.get('image'):
    #                             item['content_html'] += utils.add_image(step['image']['url'])
    #                         for it in step['itemListElement']:
    #                             item['content_html'] += '<p>{}</p>'.format(it['text'])
    #         elif '/products/' in item['url']:
    #             soup = BeautifulSoup(page_html, 'lxml')
    #             el = soup.find(class_='why-buy')
    #             if el:
    #                 if el.h4:
    #                     el.h4.decompose()
    #                 item['content_html'] += '<h2>Why Buy?</h2>' + el.decode_contents()
    #             el = soup.find('table', id='specs')
    #             if el:
    #                 el.attrs = {}
    #                 it = el.find('tr', class_='table-title')
    #                 if it:
    #                     it.decompose()
    #                 item['content_html'] += '<h2>Specs</h2>' + str(el)
    return item


def format_content(content_html, item, site_json=None, module_format_content=None):
    utils.write_file(content_html, './debug/debug.html')
    split_url = urlsplit(item['url'])
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    soup = BeautifulSoup(content_html, 'html.parser')
    el = soup.find(class_='entry-content')
    if el:
        soup = el

    # Remove site-specific elements
    if site_json and site_json.get('decompose'):
        for it in site_json['decompose']:
            for el in soup.find_all(it['tag'], attrs=it['attrs']):
                el.decompose()
    if site_json and site_json.get('unwrap'):
        for it in site_json['unwrap']:
            for el in soup.find_all(it['tag'], attrs=it['attrs']):
                el.unwrap()

    # Format module specific content
    if module_format_content:
        module_format_content(soup, item, site_json=None)

    el = soup.find(class_='blog-post-info')
    if el:
        el.unwrap()

    # Use site-specific elements when possible
    # for el in soup.find_all(class_=re.compile(r'ad-aligncenter|c-message_kit__gutter|daily_email_signup||figma-framed|inline-auto-newsletter|patreon-campaign-banner|patreon-text-under-button|sailthru_shortcode|simpletoc-|staticendofarticle|steps-shortcut-wrapper|yoast-table-of-contents|wp-polls')):
    #     el.decompose()

    for el in soup.find_all(class_=re.compile(r'^ad_|\bad\b|injected-related-story|link-related|related_links|related-stories|sharedaddy|wp-block-bigbite-multi-title|wp-block-product-widget-block')):
        el.decompose()

    for el in soup.find_all(id=re.compile(r'^ad_|\bad\b|related')):
        el.decompose()

    for el in soup.find_all('section', class_=re.compile('wp-block-newsletterglue')):
        el.decompose()

    for el in soup.find_all(id=['ez-toc-container', 'toc_container']):
        el.decompose()

    for el in soup.find_all('noscript'):
        el.decompose()

    for el in soup.find_all(id='piano-meter-offer'):
        el.unwrap()

    for el in soup.find_all('div', class_=re.compile(r'GutenbergParagraph_gutenbergParagraph_')):
        el.unwrap()

    for el in soup.find_all('div', class_=re.compile(r'gb-grid-wrapper|gb-container')):
        for it in el.find_all(class_='gb-inside-container'):
            el.insert_before(it)
            it.unwrap()
        el.decompose()

    for el in soup.find_all('svg', attrs={"data-icon": True}):
        new_html = ''
        if el['data-icon'] == 'clock':
            new_html = '<span>&#128337;</span>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled svg data-icon {} in {}'.format(el['data-icon'], item['url']))

    for el in soup.find_all('img', class_='emoji'):
        new_html = ''
        split_src = urlsplit(el['src'])
        if split_src.netloc == 's.w.org':
            src_paths = list(filter(None, split_src.path[1:].split('/')))
            m = re.findall(r'([0-9a-f]+)', src_paths[-1])
            if m:
                new_html = '<span>'
                for it in m:
                    new_html += '&#{};'.format(int(it, 16))
                    #new_html += '&#x{};'.format(it)
                new_html += '</span>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled emoji in ' + item['url'])

    for el in soup.find_all(re.compile(r'^h\d')):
        it = el.find(attrs={"style": True})
        if it:
            it.unwrap()

    for el in soup.find_all(['h5', 'h6']):
        # too small
        el.name = 'h4'

    for el in soup.find_all(class_='summary__title'):
        new_html = '<h2>{}</h2>'.format(el.get_text())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-group'):
        if el.find(id='mc_embed_signup'):
            el.decompose()

    for el in soup.find_all(class_='wp-block-prc-block-subtitle'):
        new_html = '<p><em>{}</em></p>'.format(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        soup.insert(0, new_el)
        el.decompose()

    for el in soup.find_all('p', class_=['has-drop-cap', 'dropcap', 'drop-cap']):
        new_html = re.sub(r'>("?\w)', r'><span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', str(el), 1)
        new_html += '<span style="clear:left;"></span>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('span', class_=['dropcap', 'drop-cap']):
        el.attrs = {}
        el['style'] = 'float:left; font-size:4em; line-height:0.8em;'
        new_el = BeautifulSoup('<span style="clear:left;"></span>', 'html.parser')
        el.find_parent('p').insert_after(new_el)

    for el in soup.find_all(class_='c-message_actions__container'):
        # https://theathletic.com/3900893/2022/11/16/deshaun-watson-return-browns/
        it = el.find(class_='c-message_actions__group')
        it.name = 'p'
        it.attrs = {}
        el.insert_after(it)
        el.decompose()

    for el in soup.find_all(class_='aawp'):
        # https://home-assistant-guide.com/review/xiaomi-mi-robot-vacuum-mop-1c-long-term-review-a-cheap-option-that-integrates-with-home-assistant/
        # https://home-assistant-guide.com/review/adguard-home-vs-pi-hole-2020-two-ad-and-internet-tracker-blockers-compared/
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find('a', class_=['aawp-product__image-link', 'aawp-product__image--link'])
        if it:
            img = it.find('img')
            if img:
                img_src = ''
                if img.get('data-src'):
                    img_src = img['data-src']
                elif img.get('src'):
                    img_src = img['src']
                if img_src:
                    new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><a href="{}"><img style="width:100%;" src="{}"/></a></div>'.format(it['href'], img_src)
        new_html += '<div style="flex:2; min-width:256px;">'
        it = el.find('a', class_='aawp-product__title')
        if it:
            new_html += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(it['href'], it.get_text().strip())
        it = el.find(class_='aawp-product__price')
        if it:
            new_html += '<div>{}</div>'.format(it.get_text().strip())
        it = el.find('a', class_='aawp-button')
        if it:
            new_html += '<div><a href="{}">{}</a></div>'.format(it['href'], it.get_text().strip())
        new_html += '</div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(id=re.compile(r'the-good|the-bad|the-ugly')):
        el.attrs = {}
        new_html = '<ul>'
        for it in el.find_next_siblings():
            if it.get('class') and 'gb-headline' in it['class']:
                new_html += '<li>{}</li>'.format(it.get_text())
                it.decompose()
            else:
                break
        new_html += '</ul>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)

    for el in soup.find_all(class_='wp-block-columns'):
        # https://jamesachambers.com/radxa-zero-debian-ssd-boot-guide/
        new_html = '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for it in el.find_all(class_='wp-block-column'):
            img = it.find(class_='wp-block-image')
            if img and img.img:
                if img.img.get('srcset'):
                    img_src = utils.image_from_srcset(img.img['srcset'], 160)
                else:
                    img_src = img.img['src']
                new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><img style="width:100%;" src="{}"/></div>'.format(img_src)
            else:
                new_html += '<div style="flex:2; min-width:256px;">{}</div>'.format(it.decode_contents())
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='review-wrapper'):
        # https://the5krunner.com/2023/01/11/magene-l508-review-smart-radar-tail-light/
        review_html = '<div>'
        it = el.find('img')
        if it:
            review_html += '<img src="{}" style="float:left; margin-right:8px; width:128px;"/>'.format(it['src'])
            it.decompose()
        else:
            review_html += '<img src="{}/image?width=24&height=24&color=none" style="float:left; margin-right:8px;"/>'.format(config.server)
        review_html += '<div style="overflow:hidden;">'
        it = el.find(class_='review-title')
        if it:
            review_html += '<p style="font-size:1.2em; font-weight:bold;">{}</p>'.format(it.get_text().strip())
        review_html += '</div><div style="clear:left;">&nbsp;</div>'
        it = el.find(class_='review-total-box')
        if it:
            review_html += '<h3>Score: <span style="font-size:2em; font-weight:bold;">{}</span></h3>'.format(it.get_text())
        else:
            review_html += '<h3>Scores</h3>'
        it = el.find(class_='review-list')
        if it:
            review_html += '<table style="margin-left:1.5em;">'
            for li in it.find_all('li'):
                review_html += '<tr><td>{}</td>'.format(re.sub(r' - [\d\s%]+$', '', li.get_text().strip()))
                score = ''
                result = li.find('div', class_='review-result-text')
                if result:
                    score = result.get_text().strip()
                else:
                    result = li.find('div', class_='review-result', attrs={"style": re.compile(r'width:\d+')})
                    if result:
                        m = re.search(r'width:(\d+)', result['style'])
                        if m:
                            score = '{:.1f}'.format(int(m.group(1)) / 20)
                if score:
                    review_html += '<td>{}</td></tr>'.format(score)
                else:
                    review_html += '<td></td></tr>'
            review_html += '</table>'
        it = el.find(class_='review-desc')
        if it:
            review_html += '<h3>Summary</h3><div style="margin-left:1.5em;">{}</div>'.format(it.decode_contents())
        it = el.find(class_='review-pros')
        if it:
            review_html += '<h3>Pros</h3>' + str(it.find('ul'))
        it = el.find(class_='review-cons')
        if it:
            review_html += '<h3>Pros</h3>' + str(it.find('ul'))
        it = el.find('ul', class_='review-links')
        if it:
            review_html += '<h3>Links</h3>' + str(it)
        new_el = BeautifulSoup(review_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='reviewBox'):
        # https://twinfinite.net/2023/01/one-piece-odyssey-review/
        review_html = ''
        it = el.find('img', class_='review-image')
        if it:
            review_html += utils.add_image(resize_image(it['src']))
        it = el.find(class_='review-title')
        if it:
            review_html += '<div style="text-align:center; font-size:1.3em; font-weight:bold">{}</div>'.format(it.get_text().strip())
        it = el.find(class_='reviewScoreVal')
        if it:
            review_html += '<div style="text-align:center;"><span style="font-size:2em; font-weight:bold;">{}</span>'.format(it.get_text().strip())
            it = el.find(class_='outOF')
            if it:
                review_html += ' {}'.format(it.get_text().strip())
            it = el.find(class_='review-highlight')
            if it:
                review_html += '<br/><span style="font-size:1.2em; font-style:italic;">{}</span>'.format(it.get_text().strip())
            it = el.find('img', attrs={"src": re.compile(r'Editors-Choice')})
            if it:
                review_html += '<br/><img src="{}" style="width:128px;"/>'.format(resize_image(it['src'], 128))
            it = el.find(class_='officialScore')
            if it:
                review_html += '<p>{}</p>'.format(it.decode_contents())
            review_html += '</div>'
        for it in el.find_all(class_='reviewPros'):
            review_html += '<h3>{}</h3><ul>'.format(it.h4.get_text().strip())
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text().strip())
            review_html += '</ul>'
        it = el.find(class_='gameInfo')
        if it:
            review_html += '<h3>Game info</h3><ul>'
            for li in it.find_all('div', class_=True):
                review_html += '<li>{}: '.format(li.span.extract().get_text().strip())
                review_html += '{}</li>'.format(li.get_text().strip())
            review_html += '</ul>'
        new_el = BeautifulSoup(review_html, 'html.parser')
        if el.parent and el.parent.name == 'div':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()
        it = soup.find(class_='reviewLabBox')
        if it:
            it.decompose()

    for el in soup.find_all(id='review-body'):
        # This is probably specific to techhive.com
        review_html = '<br/><div><div style="text-align:center">'
        if el.find('img', src=re.compile(r'Editors-Choice')):
            review_html += '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
        it = el.find(class_='starRating')
        if it:
            m = re.search(r'([\d\.]+) out of 5', it['aria-label'])
            if m:
                review_html += '<h1 style="margin:0;">{} / 5</h1>'.format(m.group(1))
        review_html += '</div>'
        it = el.find('p', class_='verdict')
        if it:
            review_html += '<p><em>{}</em></p>'.format(it.get_text())
        it = el.find('ul', class_='pros')
        if it:
            review_html += '<strong>Pros</strong><ul>'
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text())
            review_html += '</ul>'
        it = el.find('ul', class_='cons')
        if it:
            review_html += '<strong>Cons</strong><ul>'
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text())
            review_html += '</ul>'
        it = el.find('p', class_='verdict')
        if it:
            it.attrs = {}
            review_html += '<strong>Our Verdict</strong>' + str(it)

        it = soup.find(class_='review-best-price')
        if it:
            for sib in it.next_siblings:
                if sib.name:
                    break
            if sib.get('class') and 'wp-block-price-comparison' in sib['class']:
                review_html += '<strong>Best Prices Today</strong><ul>'
                for record in sib.find_all(class_='price-comparison__record'):
                    if 'price-comparison__record--header' in record['class'] or 'price-comparison__record--footer' in record['class']:
                        continue
                    price = record.find(class_='price-comparison__price').get_text().strip()
                    image = record.find(class_='price-comparison__image')
                    if image.img:
                        vendor = image.img['alt']
                    else:
                        vendor = image.get_text().strip()
                    review_html += '<li>{} from <a href="{}">{}</a></li>'.format(price, utils.get_redirect_url(record.a['href']), vendor)
                review_html += '</ul>'
                sib.decompose()
            it.decompose()

        it = soup.find(class_='review-price')
        if it:
            for sib in it.next_siblings:
                if sib.name:
                    break
            sib.decompose()
            it.decompose()

        review_html += '<hr style="width:80%;"/>'
        new_el = BeautifulSoup(review_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='ebook-link-wrapper'):
        new_html = ''
        it = el.find('img')
        if it:
            new_html += '<img src="{}" style="float:left; margin-right:8px; width:128px;"/>'.format(it['src'])
        else:
            new_html += '<img src="{}/image?width=24&height=24&color=none" style="float:left; margin-right:8px;"/>'.format(config.server)
        new_html += '<div style="overflow:hidden;">'
        it = el.find('h3')
        if it:
            new_html += str(it)
        if el.find('ul', class_='ebook-links'):
            new_html += '<ul>'
            for it in el.find_all('a', attrs={"data-book-store": True}):
                new_html += '<li><a href="{}">{}</a></li>'.format(it['href'], it['data-book-store'])
            new_html += '</ul>'
        new_html += '</div><div style="clear:left;"></div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='su-box'):
        new_html = '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        content = el.find(class_='su-box-content')
        img_src = ''
        link = ''
        for it in content.find_all():
            img = it.find('img')
            if img:
                img_src = img['src']
                if img.parent and img.parent.name == 'a':
                    link = it['href']
                it.decompose()
                break
        if img_src and link:
            new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><a href="{}"><img style="width:100%;" src="{}"/></a></div>'.format(link, img_src)
        elif img_src:
            new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><img style="width:100%;" src="{}"/></div>'.format(img_src)
        new_html += '<div style="flex:2; min-width:256px;">'
        it = el.find(class_='su-box-title')
        if it and link:
            new_html += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(link, it.get_text())
        elif it:
            new_html += '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(it.get_text())
        new_html += '<div>{}</div>'.format(content.decode_contents())
        new_html += '</div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-snopes-fact-check-claim'):
        new_html = '<br/><table style="width:95%; margin-left:auto; margin-right:auto; border-collapse:collapse;">'
        it = el.find(class_='card-header')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><h2 style="margin:0;">{}</h2></td></tr>'.format(it.get_text())
        it = el.find(class_='card-body')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><span style="font-size:1.2em;">{}</span></td></tr>'.format(it.decode_contents())
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-snopes-fact-check-rating'):
        new_html = '<br/><table style="width:95%; margin-left:auto; margin-right:auto; border-collapse:collapse;">'
        it = el.find(class_='card-header')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><h2 style="margin:0;">{}</h2></td></tr>'.format(it.get_text())
        for body in el.find_all(class_='card-body'):
            img = body.find('img')
            if img:
                rating = body.find(class_=re.compile(r'rating-label'))
                if img and rating:
                    new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><table><tr><td><img src="{}" style="width:120px;"/></td><td style="vertical-align:top;"><h2 style="margin:0;">{}</h2>'.format(img['src'], rating.get_text())
                    link = body.find('a')
                    if link:
                        new_html += '<a href="{}">{}</a></td></tr></table></td></tr>'.format(link['href'], link.get_text())
                    else:
                        new_html += '</td></tr></table></td></tr>'
            else:
                it = body.find(class_='media-body')
                if it.span:
                    it.span.attrs = {}
                    it.span.name = 'h3'
                new_html += '<tr><td style="border:1px solid black; padding:0.5em;">{}</td></tr>'.format(it.decode_contents())
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('figure', class_='wp-block-embed'):
        new_html = None
        if 'wp-block-embed-youtube' in el['class']:
            it = el.find('iframe')
            if it:
                if it.get('data-src'):
                    new_html = utils.add_embed(it['data-src'])
                else:
                    new_html = utils.add_embed(it['src'])
            elif el.find(class_='epyt-video-wrapper'):
                it = el.find(class_='__youtube_prefs__')
                if it:
                    new_html = utils.add_embed(it['data-facadesrc'])
            elif el.find(class_='lyte-wrapper'):
                # https://hometheaterreview.com/formovie-theater-ust-4k-projector-review/
                it = el.find('meta', attrs={"itemprop": "embedURL"})
                if it:
                    new_html = utils.add_embed(it['content'])
        elif 'wp-block-embed-twitter' in el['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif 'wp-block-embed-instagram' in el['class']:
            it = el.find('blockquote')
            if it:
                new_html = utils.add_embed(it['data-instgrm-permalink'])
        elif 'wp-block-embed-tiktok' in el['class']:
            it = el.find('blockquote')
            if it:
                new_html = utils.add_embed(it['cite'])
        elif 'wp-block-embed-facebook' in el['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif el.find('video'):
            it = el.find('source')
            if it:
                poster = '{}/image?url={}'.format(config.server, quote_plus(it['src']))
                new_html = utils.add_video(it['src'], it['type'], poster)
        else:
            it = el.find('iframe')
            if it:
                if it.get('data-src'):
                    new_html = utils.add_embed(it['data-src'])
                else:
                    new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-embed in ' + item['url'])

    for el in soup.find_all(class_='jetpack-video-wrapper'):
        new_html = ''
        if el.find(class_=['embed-vimeo', 'embed-youtube']):
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled jetpack-video-wrapper in ' + item['url'])

    for el in soup.find_all(class_='nbcsports-video-wrapper'):
        new_html = ''
        if el.iframe and el.iframe.get('data-mpx-src'):
            page_html = utils.get_url_html(el.iframe['data-mpx-src'])
            page_soup = BeautifulSoup(page_html, 'lxml')
            it = page_soup.find('link', attrs={"type": "application/smil+xml"})
            if it:
                video_src = utils.get_redirect_url(it['href'])
                if re.search('.mp4', video_src, flags=re.I):
                    video_type = 'video/mp4'
                else:
                    video_type = 'application/x-mpegURL'
                it = page_soup.find('meta', attrs={"property": "og:image"})
                if it:
                    poster = it['content']
                else:
                    poster = ''
                it = page_soup.find('meta', attrs={"property": "og:description"})
                if it:
                    caption = it['content']
                else:
                    caption = ''
            new_html = utils.add_video(video_src, video_type, poster, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        if not new_html:
            logger.warning('unhandled nbcsports-video-wrapper in ' + item['url'])

    for el in soup.find_all(class_='epyt-video-wrapper'):
        it = el.find(class_='__youtube_prefs__')
        if it:
            if it.get('data-facadesrc'):
                new_html = utils.add_embed(it['data-facadesrc'])
            else:
                new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled epyt-video-wrapper in ' + item['url'])

    for el in soup.find_all(class_='elementor-element'):
        new_html = ''
        if 'elementor-widget-video' in el['class']:
            data_json = json.loads(el['data-settings'])
            if data_json['video_type'] == 'youtube':
                new_html = utils.add_embed(data_json['youtube_url'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled elementor-element in ' + item['url'])

    for el in soup.find_all(class_='sketchfab-embed-wrapper'):
        new_html = ''
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled sketchfab-embed-wrapper in ' + item['url'])

    for el in soup.find_all(class_='infogram-embed'):
        if el.get('data-id'):
            new_html = utils.add_embed('https://e.infogram.com/{}?src=embed'.format(el['data-id']))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled infogram-embed in ' + item['url'])

    for el in soup.find_all(class_=['gallery', 'tiled-gallery', 'wp-block-gallery', 'wp-block-jetpack-tiled-gallery', 'article-slideshow', 'wp-block-jetpack-slideshow', 'ess-gallery-container', 'inline-slideshow', 'm-carousel', 'multiple-images', 'image-pair', 'undark-image-caption']):
        if set(['gallery', 'tiled-gallery', 'wp-block-gallery', 'wp-block-jetpack-tiled-gallery']).intersection(el['class']):
            if el.find('ul', class_='gallery-wrap'):
                images = el.find_all('li')
                caption = True
            else:
                images = [img for img in el.find_all('img') if (img.get('class') and 'carousel-thumbnail' not in img['class'])]
                caption = False
        elif set(['article-slideshow', 'wp-block-jetpack-slideshow']).intersection(el['class']):
            images = el.find_all('li')
            caption = True
        elif 'ess-gallery-container' in el['class']:
            # https://www.essence.com/entertainment/beyonce-dubai-atlantis-the-royal-grand-reveal-performance/
            images = el.find_all(class_='gallery-slide')
            caption = True
        elif 'inline-slideshow' in el['class']:
            # https://trendeepro.com/like-emily-ratajkowski-im-a-mom-who-takes-my-baby-to-work/
            images = el.find_all(class_='inline-slideshow__slide')
            caption = True
        elif 'm-carousel' in el['class']:
            # https://www.digitaltrends.com/mobile/oneplus-11-review/
            images = el.find_all('figure', class_='m-carousel--content')
            caption = True
        elif 'multiple-images' in el['class']:
            # https://themarkup.org/news/2023/02/08/how-big-tech-rewrote-the-nations-first-cellphone-repair-law
            images = el.find_all('li', class_='multiple-images__item')
            caption = False
        elif 'image-pair' in el['class']:
            images = el.find_all('figure', class_='image-pair__figure')
            caption = True
        elif 'undark-image-caption' in el['class']:
            # https://undark.org/2023/02/22/how-an-early-warning-radar-could-prevent-future-pandemics/
            images = el.find_all(class_='cell')
            caption = True
        gallery_parent = el.find_parent('div', id=re.compile(r'attachment_\d'))
        if not gallery_parent:
            gallery_parent = el
        n = len(images) - 1
        for i, img in enumerate(images):
            if i < n:
                add_image(img, gallery_parent, base_url, caption, False, True, i+1)
            else:
                add_image(img, gallery_parent, base_url, True, False, True, i+1)
            img.decompose()
        gallery_parent.decompose()

    for el in soup.find_all(class_='pbslideshow-wrapper'):
        # https://www.playstationlifestyle.net/2023/01/23/forspoken-review-ps5-worth-playing
        page_html = utils.get_url_html(item['url'])
        page_soup = BeautifulSoup(page_html, 'lxml')
        it = page_soup.find('script', string=re.compile(r'wpQueryVars'))
        if not it:
            logger.warning(r'unable to find wpQueryVars in ' + item['url'])
            continue
        m = re.search(r'query : \'([^\']+)\'', it.string, flags=re.S)
        if not m:
            logger.warning(r'unable to parse wpQueryVars in ' + item['url'])
            continue
        query = m.group(1)
        it = el.find(id=re.compile(r'ngg-gallery-\d+-\d+'))
        if not it:
            logger.warning(r'unhandled pbslideshow-wrapper with no ngg-gallery in ' + item['url'])
            continue
        m = re.search(r'ngg-gallery-(\d+)-(\d+)', it['id'])
        slideshow_id = m.group(1)
        page_html = utils.get_url_html('{}/index.php?action=get_slideshow&slideshow_id={}&template=desktopview&imagetag=&query={}'.format(base_url, slideshow_id, quote_plus(query)))
        if not page_html:
            logger.warning('unable to get_slideshow for ' + item['url'])
            continue
        utils.write_file(page_html, './debug/slideshow.html')
        page_soup = BeautifulSoup(page_html, 'html.parser')
        images = page_soup.find_all(class_='pbslideshow-slider-item')
        desc = page_soup.find_all(class_='pbslideshow-description-inner')
        new_html = '<h2>Gallery</h2>'
        for i, it in enumerate(images):
            if desc[i].get_text().strip():
                new_html += utils.add_image(it['data-pbslazyurl'], desc=str(desc[i]))
            else:
                new_html += utils.add_image(it['data-pbslazyurl'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='foogallery'):
        # https://techaeris.com/2022/12/20/steelseries-aerox-5-wireless-review-stellar-mouse-varying-battery-life/
        for it in el.find_all(class_='fg-item'):
            new_html = ''
            img = it.find('a', class_='fg-thumb')
            if img:
                img_src = img['href']
                if img_src.startswith('/'):
                    img_src = base_url + img_src
                if img.get('data-caption-title'):
                    caption = img['data-caption-title']
                elif it.find(class_='fg-caption-title'):
                    caption = it.find(class_='fg-caption-title').get_text().strip()
                else:
                    caption = ''
                new_html = utils.add_image(resize_image(img_src), caption)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_before(new_el)
            else:
                logger.warning('unhandled article-slideshow image')
        el.decompose()

    for el in soup.find_all(class_=re.compile(r'bp-embedded-image|captioned-image-container|entry-image|gb-block-image|pom-image-wrap|post-content-image|wp-block-image|wp-caption|wp-image-\d+|wp-block-media')):
        add_image(el, None, base_url)

    for el in soup.find_all('figure', id=re.compile(r'media-\d+')):
        add_image(el, None, base_url)

    #for el in soup.find_all('img', class_='post-image'):
    for el in soup.find_all(lambda tag:tag.name == "img" and
            (('class' in tag.attrs and 'post-image' in tag.attrs['class']) or
             ('alt' in tag.attrs) or
             ('decoding' in tag.attrs)
            )):
        if el.parent and el.parent.name == 'a' and el.parent.get('class') and 'app-icon' in el.parent['class']:
            continue
        elif el.get('class') and 'ql-img-inline-formula' in el['class']:
            # https://www.logicmatters.net/2023/02/15/does-mathematics-need-a-philosophy/
            if el['src'].startswith('data:'):
                el['src'] = el['data-src']
            continue
        add_image(el, None, base_url)

    for el in soup.find_all(class_='media-wrapper'):
        # Used on macstories.net
        new_html = ''
        if 'subscribe-podcast-cta' in el['class']:
            el.decompose()
        elif 'audio-player' in el['class']:
            it = el.find('source')
            if it:
                new_html = '<div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Play</a></span></div>'.format(it['src'], config.server)
        elif el.find(class_='image-caption'):
            img_src = el.img['src']
            if img_src.startswith('/'):
                img_src = base_url + img_src
            it = el.find(class_='image-caption')
            if it:
                caption = it.get_text().strip()
            else:
                caption = ''
            new_html = utils.add_image(resize_image(img_src), caption)
        elif el.find('iframe', class_='youtube-player'):
            new_html = utils.add_embed(el.iframe['src'])
        elif el.find('iframe', attrs={"src": re.compile(r'podcasts\.apple\.com')}):
            new_html = utils.add_embed(el.iframe['src'])
        else:
            logger.warning('unhandled media-wrapper class {}'.format(el['class']))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='video-player'):
        # https://stratechery.com/2022/microsoft-full-circle/
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.get('align'):
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled video-player in ' + item['url'])

    for el in soup.find_all(class_='wp-block-video'):
        video_src = ''
        if el.video:
            video_src = el.video.get('src')
            poster = el.video.get('poster')
            if not video_src:
                if el.video.source:
                    video_src = el.video.source['src']
        if video_src:
            if re.search(r'\.mp4', video_src) or re.search(r'\.mov', video_src):
                video_type = 'video/mp4'
            elif re.search(r'\.webm', video_src):
                video_type = 'video/webm'
            elif re.search(r'\.m3u8', video_src):
                video_type = 'application/x-mpegURL'
            else:
                logger.warning('unhandled video type for {} in {}'.format(video_src, item['url']))
                video_container = av.open(video_src)
                if 'mp4' in video_container.format.extensions:
                    video_type = 'video/mp4'
                elif 'webm' in video_container.format.extensions:
                    video_type = 'video/webm'
                else:
                    video_type = 'application/x-mpegURL'
                video_container.close()
            if not poster:
                if video_type == 'video/mp4':
                    poster = '{}/image?url={}&width=1000'.format(config.server, quote_plus(video_src))
                else:
                    poster = '{}/image?width=1000&height=563'.format(config.server)
            if el.figcaption:
                caption = el.figcaption.decode_contents()
            else:
                caption = ''
            new_el = BeautifulSoup(utils.add_video(video_src, video_type, poster, caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-video in ' + item['url'])

    for el in soup.find_all(class_=['wp-block-audio', 'wp-audio-shortcode']):
        audio_src = ''
        if el.name == 'audio':
            audio = el
        else:
            audio = el.find('audio')
        if audio:
            if audio.get('src'):
                audio_src = audio['src']
            else:
                it = el.find('source')
                if it:
                    audio_src = it['src']
        if audio_src:
            it = el.find(class_='wp-element-caption')
            if it:
                caption = it.get_text()
            else:
                caption = 'Play'
            new_html = '<div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">{2}</a></span></div>'.format(audio_src, config.server, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-audio in ' + item['url'])

    for el in soup.find_all(class_='podcast'):
        # https://www.wired.com/author/geeks-guide-to-the-galaxy/
        poster = '{}/image?&width=256&overlay=audio'.format(config.server)
        it = el.find('img')
        if it:
            poster += '&url=' + quote_plus(it['src'])
        it = el.find('audio')
        if it:
            audio_src = it.source['src']
        else:
            audio_src = ''
        new_html = '<div><a href="{}"><img src="{}"/></a></div>'.format(audio_src, poster)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='embed-youtube'):
        new_html = ''
        if el.iframe:
            if el.iframe.get('src'):
                new_html = utils.add_embed(el.iframe['src'])
            elif el.iframe.get('data-src'):
                new_html = utils.add_embed(el.iframe['data-src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embed-youtube in ' + item['url'])

    for el in soup.find_all(class_='video-container'):
        new_html = ''
        if el.find(class_='js-video') or 'pmYTPlayerContainer' in el['class']:
            new_html = utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(el['id']))
        else:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled video-container in ' + item['url'])

    for el in soup.find_all(class_='dtvideos-container'):
        if el.get('data-provider') and el['data-provider'] == 'youtube':
            it = el.find(class_='h-embedded-video')
            if it:
                new_el = BeautifulSoup(utils.add_embed(it['data-url']), 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhanlded youtube dtvideo-container in ' + item['url'])
        else:
            logger.warning('unhandled dtvideos-container in ' + item['url'])

    for el in soup.find_all(attrs={"data-embed-type": "Brightcove"}):
        it = el.find('video')
        if it:
            new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(it['data-account'], it['data-player'], it['data-video-id']))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled Brightcove embed in ' + item['url'])

    for el in soup.find_all('video', class_='video-js'):
        new_html = ''
        if el.get('data-player'):
            new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(el['data-account'], el['data-player'], el['data-video-id']))
        elif el.get('data-opts'):
            data_opts = json.loads(el['data-opts'])
            source = utils.closest_dict(data_opts['plugins']['sources']['renditions'], 'frameHeight', 480)
            if source['videoContainer'] == 'MP4':
                video_type = 'video/mp4'
            else:
                video_type = 'application/x-mpegURL'
            new_html = utils.add_video(source['url'], video_type, data_opts['poster'], data_opts['title'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el_parent = el
            while el_parent.parent.parent:
                el_parent = el_parent.parent
            el_parent.insert_after(new_el)
            el_parent.decompose()
        else:
            logger.warning('unhandled video-js embed in ' + item['url'])

    for el in soup.find_all(class_='blogstyle__iframe'):
        new_html = ''
        it = el.find('iframe')
        if it:
            if it.get('src'):
                new_html = utils.add_embed(it['src'])
            elif it.get('data-src'):
                new_html = utils.add_embed(it['data-src'])
            else:
                logger.warning('unknown iframe src in ' + item['url'])
        else:
            it = el.find(class_='twitter-tweet')
            if it:
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled blogstyle__iframe in ' + item['url'])

    for el in soup.find_all('iframe'):
        el_parent = el
        for it in reversed(el.find_parents()):
            if it.name == 'p':
                has_str = False
                for c in it.contents:
                    if isinstance(c, bs4.element.NavigableString):
                        has_str = True
                if not has_str:
                    el_parent = it
                    break
            elif not it.find('p'):
                el_parent = it
                break

        if el.get('src'):
            src = el['src']
        elif el.get('data-src'):
            src = el['data-src']
            src = el['data-src']
        else:
            src = ''
        if src:
            if not re.search(r'amazon-adsystem\.com', src):
                new_el = BeautifulSoup(utils.add_embed(src), 'html.parser')
                el_parent.insert_after(new_el)
                el_parent.decompose()
        else:
            logger.warning('unknown iframe src in ' + item['url'])

    for el in soup.find_all(class_='twitter-tweet'):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(attrs={"data-initial-classes": "twitter-tweet"}):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='tiktok-embed'):
        new_el = BeautifulSoup(utils.add_embed(el['cite']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='pull-number'):
        # https://themarkup.org/privacy/2023/02/16/forget-milk-and-eggs-supermarkets-are-having-a-fire-sale-on-data-about-you
        it = el.find(class_='pull-number__content')
        if it:
            author = el.find(class_='pull-number__source')
            if author:
                new_html = utils.add_blockquote(it.decode_contents() + '<small>{}</small>'.format(author.decode_contents()))
            else:
                new_html = utils.add_blockquote(it.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled pull-number in ' + item['url'])

    for el in soup.find_all(class_='quote'):
        it = el.find(class_='quote__text')
        if it:
            # TODO: citation/author?
            new_html = utils.add_pullquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_=['pullquote', 'wp-block-pullquote', 'simplePullQuote', 'undark-pull-quote']):
        if el.blockquote:
            el.blockquote.unwrap()
        it = el.find('cite')
        if it:
            author = it.get_text()
            it.decompose()
        else:
            author = ''
        it = el.find(class_='soundcite')
        if it:
            it.decompose()
        it = el.find(class_='blockquote-text')
        if it:
            new_html = utils.add_pullquote(it.decode_contents(), author)
        else:
            it = el.find(class_='undark-quote')
            if it:
                new_html = utils.add_pullquote(it.get_text().strip(), author)
            else:
                new_html = utils.add_pullquote(el.decode_contents(), author)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('blockquote'):
        if el.name == None or re.search(r'^Embedded content from', el.get_text()):
            # Likely a nested blockquote which won't get styled
            continue
        new_html = ''
        if el.get('class'):
            if 'instagram-media' in el['class']:
                new_html = utils.add_embed(el['data-instgrm-permalink'])
            elif el.find('code'):
                el.attrs = {}
                el.name = 'pre'
                continue
            elif 'wp-block-quote' in el['class'] or 'wp-block-pullquote' in el['class'] or 'puget-blockquote' in el['class']:
                it = el.find('cite')
                if it:
                    author = it.get_text()
                    it.decompose()
                else:
                    author = ''
                it = el.find(class_='blockquote-text')
                if it:
                    new_html = utils.add_pullquote(it.decode_contents(), author)
                else:
                    new_html = utils.add_pullquote(el.decode_contents(), author)
        if not new_html:
            if el.get('id') and re.search(r'blockquote\d', el['id']):
                new_html = utils.add_blockquote(el.decode_contents())
            else:
                it = el.find(class_='quote-author')
                if it:
                    author = it.get_text().strip()
                    if author == 'by':
                        author = ''
                    it.decompose()
                    new_html = utils.add_pullquote(el.decode_contents(), author)
                else:
                    if el.get_text().strip():
                        new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-prc-block-collapsible'):
        new_html = ''
        it = el.find(class_='wp-block-prc-block-collapsible__title')
        if it:
            new_html += '<h4>{}</h4>'.format(it.get_text().strip())
        it = el.find(class_='wp-block-prc-block-collapsible__content')
        if it:
            new_html += it.decode_contents()
        new_el = BeautifulSoup(utils.add_blockquote(new_html), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='box'):
        if 'shadow' in el['class']:
            it = el.find(class_='tieicon-boxicon')
            if it:
                it.decompose()
            it = el.find(class_='box-inner-block')
            if it:
                new_html = utils.add_blockquote(it.decode_contents())
            else:
                new_html = utils.add_blockquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('p', class_='has-background'):
        new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    # wp-block-code
    for el in soup.find_all('pre'):
        #if el.find('code') or (el.get('class') and re.search(r'bash', ', '.join(el['class']))) or re.search(r'^$|sudo|', el.get_text().strip()):
        el.attrs = {}
        el['style'] = 'margin-left:2em; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'

    for el in soup.find_all(class_='codecolorer-container'):
        el.name = 'pre'
        el.attrs = {}
        el['style'] = 'margin-left:2em; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'
        it = el.find(class_='codecolorer')
        it.name = 'code'

    for el in soup.find_all('code'):
        if el.parent:
            el['style'] = 'background:#F2F2F2;'
        else:
            new_html = '<pre style="margin-left:2em; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;">{}</pre>'.format(str(el))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='article-pull-quote'):
        quote = el.find(class_='text')
        if quote:
            it = el.find(class_='author')
            if it:
                author = it.get_text()
            else:
                author = ''
            new_el = BeautifulSoup(utils.add_pullquote(quote.decode_contents(), author), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled article-pull-quote')

    for el in soup.find_all(class_='media-element'):
        it = el.find('img', class_='media-element-image')
        if it:
            new_html = '<table><tr><td style="width:128px;"><img src="{}" style="width:100%;"></td><td>'.format(it['src'])
            desc = el.find(class_='media-element-description')
            if desc:
                it = desc.find(class_='title')
                if it:
                    it.name = 'h4'
                    it.attrs = {}
                    it['style'] = 'margin-top:0; margin-bottom:0.5em;'
                desc = desc.decode_contents()
                desc = re.sub(r'</p>\s*<p>', '<br/><br/>', desc)
                desc = re.sub(r'<p>|</p>', '', desc)
                new_html += desc
            new_html += '</td></tr></table>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled media-element')

    for el in soup.find_all(class_='bottom-line-module'):
        it = el.find(class_='module-title')
        if it:
            it.name = 'h4'
            it.attrs = {}
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_='is-content-justification-center'):
        el.attrs = {}
        el['style'] = 'text-align:center;'

    for el in soup.find_all('a', href=re.compile(r'^/')):
        el['href'] = base_url + el['href']

    for el in soup.find_all('img', src=re.compile(r'^/')):
        el['src'] = base_url + el['src']

    for el in soup.find_all('a', href=re.compile(r'go\.redirectingat\.com/')):
        el['href'] = utils.get_redirect_url(el['href'])

    for el in soup.find_all(class_='product-link'):
        href = utils.get_redirect_url(el['href'])
        el.attrs = {}
        el['href'] = href

    for el in soup.find_all(class_='wp-block-product-widget-block'):
        if el.find(id='mentioned-in-this-article'):
            el.decompose()

    for el in soup.find_all(['aside', 'ins', 'script', 'style']):
        el.decompose()

    if not item.get('_image'):
        el = soup.find('img')
        if el:
            item['_image'] = el['src']

    content_html = re.sub(r'</(figure|table)>\s*<(figure|table|/li)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[-1] == 'embed':
        del paths[-1]
        args['embed'] == True

    if isinstance(site_json['posts_path'], str):
        posts_path = site_json['posts_path']
    elif isinstance(site_json['posts_path'], dict):
        key = set(paths).intersection(site_json['posts_path'].keys())
        if key:
            posts_path = site_json['posts_path'][list(key)[0]]
        else:
            posts_path = site_json['posts_path']['default']

    if site_json['wpjson_path'].startswith('/'):
        wpjson_path = '{}://{}{}'.format(split_url.scheme, split_url.netloc, site_json['wpjson_path'])
    else:
        wpjson_path = site_json['wpjson_path']

    # Try to determine the post id or slug from the path
    post = None
    for it in paths:
        if it.isnumeric() and len(it) > 4:
            post_url = '{}{}/{}'.format(wpjson_path, posts_path, it)
        elif '-' in it and not (site_json.get('exclude_slugs') and it in site_json['exclude_slugs']):
            slug = it.split('.')[0]
            m = re.search(r'-(\d{5,}$)', slug)
            if m and not (len(m.group(1)) == 8 and m.group(1).startswith('202')):
                post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1))
            else:
                post_url = '{}{}?slug={}'.format(wpjson_path, posts_path, slug)
        else:
            continue
        post = utils.get_url_json(post_url)
        if post:
            break
    if post:
        if isinstance(post, list):
            return get_post_content(post[0], args, site_json, save_debug)
        else:
            return get_post_content(post, args, site_json, save_debug)

    # Look for the post id in the page
    post_url = ''
    page_html = utils.get_url_html(url)
    if page_html:
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find('link', attrs={"rel": "alternate", "type": "application/json", "href": re.compile(r'wp-json')})
        if el:
            post_url = el['href']
        else:
            el = soup.find('link', attrs={"rel": "shortlink"})
            if el:
                query = parse_qs(urlsplit(el['href']).query)
                if query.get('p'):
                    post_url = '{}{}/{}'.format(wpjson_path, posts_path, query['p'][0])
        if not post_url:
            el = soup.find(id=re.compile(r'post-\d+'))
            if el:
                m = re.search(r'post-(\d+)', el['id'])
                if m:
                    post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1))
            else:
                el = soup.find(class_=re.compile(r'postid-\d+'))
                if el:
                    m = re.search(r'postid-(\d+)', ' '.join(el['class']))
                    if m:
                        post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1))
    if not post_url:
        logger.warning('unable to determine wp-json post url in ' + url)
        return None

    post = utils.get_url_json(post_url)
    if not post:
        return None

    return get_post_content(post, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    if '/wp-json/' in args['url']:
        n = 0
        feed = utils.init_jsonfeed(args)
        posts = utils.get_url_json(args['url'])
        if posts:
            for post in posts:
                if save_debug:
                    logger.debug('getting content from ' + post['link'])
                item = get_post_content(post, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed['items'].append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
    else:
        feed = rss.get_feed(url, args, site_json, save_debug, get_content)
    return feed

