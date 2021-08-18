import json, re
from bs4 import BeautifulSoup
from datetime import datetime

import utils
from feedhandlers import twitter, youtube

import logging
logger = logging.getLogger(__name__)

def get_image_src(el_img, width=1000, height=''):
  if el_img.has_attr('data-lazy-sized'):
    img_src = el_img['data-image-loader']
  else:
    img_src = el_img['src']

  if img_src.startswith('https://i.pcmag.com/imagery'):
    m = re.search(r'\.(size_\d+x\d+)', img_src)
    if m:
      return img_src.replace(m.group(1), 'size_{}x{}'.format(width, height))
    m = re.search(r'\.(fit_\w+)', img_src)
    if m:
      return img_src.replace(m.group(1), 'fit_lim.size_{}x{}'.format(width, height))
    m = re.search(r'\.(jpg|png)', img_src)
    if m:
      return img_src.replace(m.group(1), 'fit_lim.size_{}x{}.{}'.format(width, height, m.group(1)))
  elif el_img.has_attr('srcset'):
    return utils.image_from_srcset(el_img['srcset'], width)
  return img_src

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url, 'desktop')
  if not article_html:
    return None
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  soup = BeautifulSoup(article_html, 'html.parser')
  for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
    ld_json = json.loads(el.string)
    if ld_json.get('@type'):
      if ld_json['@type'] == 'Article':
        break
      elif ld_json['@type'] == 'Product' and ld_json.get('review'):
        ld_json = ld_json['review']

  item = {}
  item['id'] = url
  item['url'] = url
  el = soup.find('meta', attrs={"property": "og:title"})
  if el:
    item['title'] = el['content']
  else:
    item['title'] = soup.title.string

  dt = datetime.fromisoformat(ld_json['datePublished'])
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(ld_json['dateModified'])
  item['date_modified'] = dt.isoformat()

  # Check age
  if 'age' in args:
    if not utils.check_age(item, args):
      return None

  if ld_json.get('author'):
    item['author'] = {}
    if isinstance(ld_json['author'], list):
      authors = []
      for author in ld_json['author']:
        authors.append(author['name'])
      item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
      item['author']['name'] = ld_json['author']['name']

  m = re.search(r'PogoConfig = (\{[^\}]+\})', article_html)
  if m:
    pogo = json.loads(m.group(1))
    item['tags'] = []
    if pogo.get('category'):
      item['tags'].append(pogo['category'])
    if pogo.get('tags'):
      for tag in pogo['tags']:
        item['tags'].append(tag)

  el = soup.find('meta', attrs={"property": "og:image"})
  if el:
    item['_image'] = el['content']

  el = soup.find('meta', attrs={"property": "description"})
  if el:
    item['summary'] = el['content']

  article = soup.find('article')
  if not article:
    return item

  article.attrs = {}

  for el in article.find_all('img'):
    img_src = get_image_src(el)
    caption = ''
    for it in el.next_siblings:
      if not it.name:
        continue
      break
    if it.name == 'div' and it.small:
      caption = it.get_text().strip()
      it.decompose()
    new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  for el in article.children:
    if el.name == 'ins':
      el.decompose()
    elif el.name == 'div':
      if el.has_attr('x-data'):
        el.decompose()
      elif el.has_attr('id') and ('comments' in el['id'] or 'similar-products' in el['id']):
        el.decompose()
      elif el.has_attr('class') and 'review-card' in el['class']:
        el.decompose()
      elif el.h3 and re.search(r'Recommended by Our Editors', el.h3.get_text()):
        el.decompose()
      elif el.iframe:
        if el.iframe.has_attr('loading') and el.iframe['loading'] == 'lazy':
          iframe_src = el.iframe['data-image-loader']
        else:
          iframe_src = el.iframe['src']
        if 'youtube.com' in iframe_src:
          new_el = BeautifulSoup(utils.add_video(iframe_src, 'youtube'), 'html.parser')
          el.insert_after(new_el)
          el.decompose()
      elif el.find(id=re.compile(r'video-container-')):
        video_json = None
        for it in el.parent.find_all('script'):
          m = re.search(r'window\.videoEmbeds\.push\(\{.*data:\s(\{.*\}).*\}\);', str(it), flags=re.S)
          if m:
            video_json = json.loads(m.group(1))
            break
        if video_json:
          if save_debug:
            utils.write_file(video_json, './debug/video.json')
          videos = []
          for video_src in video_json['transcoded_urls']:
            m = re.search(r'\/(\d+)\.mp4', video_src)
            if m:
              video = {}
              video['src'] = video_src
              video['height'] = m.group(1)
          if videos:
            video_src = utils.closest_dict(videos, '480')
          new_el = BeautifulSoup(utils.add_video(video_src, 'video/mp4', video_json['thumbnail_url'], video_json['title']), 'html.parser')
          el.insert_after(new_el)
          el.decompose()
        else:
          logger.warning('unable to parse video json data in ' + url)

    elif el.name == 'p':
      for it in el.find_all('strong'):
        if it.a and it.a['href'] == 'https://www.pcmag.com/newsletter_manage':
          el.decompose()
          break

  if '/reviews/' in url:
    review_html = ''
    el = soup.find(ref='gallery')
    if el:
      img_src = get_image_src(el.img)
    review_html += utils.add_image(img_src)

    if ld_json.get('reviewRating'):
      review_html += '<center><h3>{} / {}'.format(ld_json['reviewRating']['ratingValue'], ld_json['reviewRating']['bestRating'])
      el = soup.find('header', id='content-header')
      if el:
        if el.img and el.img.has_attr('alt') and 'editors choice' in el.img['alt']:
          review_html += ' 	&ndash; Editors\' Choice'
      review_html += '</h3></center>'

    el = soup.find(class_='bottom-line')
    if el:
      review_html += '<h3>{}</h3>{}'.format(el.h3.get_text(), el.p)

    el = soup.find(class_='pros-cons')
    if el:
      headers = el.find_all('h3')
      for i, ul in enumerate(el.find_all('ul')):
        review_html += '<h3>{}</h3><ul>'.format(headers[i].get_text())
        for li in ul.find_all('li'):
          review_html += '<li>{}</li>'.format(li.get_text())
        review_html += '</ul>'

    el = soup.find(id='specs')
    if el:
      review_html += '<h3>{}</h3>'.format(el.get_text())
      for it in el.next_siblings:
        if it.name == None:
          continue
        break
      if it.name == 'table':
        it.attrs = {}
        for t in it.find_all(['tr', 'td']):
          t.attrs = {}
        review_html += str(it)

    if review_html:
      review_html += '<hr />'
      new_el = BeautifulSoup(review_html, 'html.parser')
      article.insert(0, new_el)

  # Add lead image
  el = soup.find(class_='article-image')
  if el:
    img_src = get_image_src(el.img)
    if el.small:
      caption = el.small.get_text()
    else:
      caption = ''
    new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
    article.insert(0, new_el)

  item['content_html'] = str(article)
  return item

def get_feed(args, save_debug=False):
  page_html = utils.get_url_html(args['url'], 'desktop')
  if not page_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(page_html)

  soup = BeautifulSoup(page_html, 'html.parser')

  n = 0
  items = []
  feed = utils.init_jsonfeed(args)
  if '/reviews' in args['url']:
    links = soup.find_all('a', attrs={"data-element":"review-title"})
  else:
    links = soup.find_all('a', attrs={"data-element":"article-title"})
  for a in links:
    url = a['href']
    if not url.startswith('https://www.pcmag.com/'):
      url = 'https://www.pcmag.com' + a['href']
    if save_debug:
      logger.debug('getting content from ' + url)
    item = get_content(url, args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed['items'] = items.copy()
  return feed
