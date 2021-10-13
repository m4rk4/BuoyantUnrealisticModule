import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_full_image(img_src):
  m = re.search(r'(https:\/\/s\.yimg\.com\/os\/creatr-uploaded-images\/[^\.]+)', img_src)
  if m:
    return m.group(1)
  m = re.search(r'image_uri=([^&]+)', img_src)
  if m:
    return unquote_plus(m.group(1))
  return img_src

def get_content(url, args, save_debug=False):
  # Some content is blocked without this header
  article_html = utils.get_url_html(url, headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"})
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  soup = BeautifulSoup(article_html, 'html.parser')
  el = soup.find('script', attrs={"type": "application/ld+json"})

  # This is a workaround for invalid json
  ld = re.sub(r',\s+,', ',', el.string)
  ld_json = json.loads(ld)
  if save_debug:
    utils.write_file(ld_json, './debug/debug.json')

  if ld_json.get('itemReviewed'):
    ld_json = ld_json['itemReviewed']['review']

  item = {}
  el = soup.find('meta', attrs={"name": "post_id"})
  if el and el.get('content'):
    item['id'] = el['content']
  else:
    item['id'] = url

  item['url'] = url

  if ld_json.get('headline'):
    item['title'] = ld_json['headline']
  else:
    item['title'] = soup.title.string

  dt_pub = None
  dt_mod = None
  tz_est = pytz.timezone('US/Eastern')
  if ld_json.get('datePublished'):
    dt = datetime.strptime(ld_json['datePublished'], '%a, %b %d %Y %H:%M:%S EDT')
    dt_pub = tz_est.localize(dt).astimezone(pytz.utc)    
  if ld_json.get('dateModified'):
    dt = datetime.strptime(ld_json['dateModified'], '%a, %b %d %Y %H:%M:%S EDT')
    dt_mod = tz_est.localize(dt).astimezone(pytz.utc)
    if not dt_pub:
      dt_pub = dt_mod
  if dt_pub:
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt_pub.strftime('%b'), dt_pub.day, dt_pub.year)
  if dt_mod:
    item['date_modified'] = dt_mod.isoformat()

  if ld_json.get('author'):
    item['author'] = {}
    if isinstance(ld_json['author'], dict):
      item['author']['name'] = ld_json['author']['name']
    elif isinstance(ld_json['author'], list):
      authors = []
      for author in ld_json['author']:
        authors.append(author['name'])
      item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
  
  item['tags'] = []
  for tag in ld_json['keywords'].split(','):
    item['tags'].append(tag)
  
  item['_image'] = get_full_image(ld_json['thumbnailUrl'])

  if ld_json.get('articleBody'):
    item['summary'] = ld_json['articleBody']
  elif ld_json.get('reviewBody'):
    item['summary'] = ld_json['reviewBody']

  # Parse the main story contents
  #article = soup.find('section', attrs={"data-component": "ArticleContainer"})

  content_html = ''
  for article_text in soup.find_all(class_='article-text'):
    for el in article_text.find_all(True):
      for attr in ['style']:
        if el.has_attr(attr):
          del el[attr]

    has_lede = False
    if not content_html:
      el = soup.find('figure', attrs={"data-component": "DefaultLede"})
      if el:
        has_lede = True
        article_text.insert(0, el)
    
    if not has_lede:
      for el in article_text.find_all_previous(class_='Pos(r)'):
        img = el.find('img')
        if img:
          if '/creatr-uploaded-images/' in img['src'] and not img['src'] in content_html:
            caption = ''
            cap = el.find(class_=re.compile(r'C\(engadgetFont(Black|Gray)\)'))
            if cap:
              caption = cap.get_text().strip()
            article_text.insert(0, BeautifulSoup(utils.add_image(get_full_image(img['src']), caption), 'html.parser'))
            break

    for el in article_text.find_all(class_='article-slideshow'):
      images = []
      captions = []
      for fig in el.find_all('figure'):
        img = fig.find('img')
        if img:
          img_src = ''
          if img.has_attr('src'):
            img_src = img.get('src')
          elif img.has_attr('data-wf-src'):
            img_src = img.get('data-wf-src')
          else:
            logger.warning('unknown img src in ' + str(img))
          images.append(img_src)

          caption = []
          el_cap = fig.find('figcaption')
          if el_cap:
            cap = el_cap.get_text().strip()
            if cap:
              caption.append(cap)
          el_cap = fig.find(class_='photo-credit')
          if el_cap:
            cap = el_cap.get_text().strip()
            if cap:
              caption.append(cap)
          captions.append(' | '.join(caption))
    
      for n in reversed(range(len(images))):
        caption = '[{}/{}] {}'.format(n+1, len(images), captions[n])
        img_src = get_full_image(images[n])
        el.insert_after(BeautifulSoup(utils.add_image(img_src, caption), 'html.parser'))

      el.decompose()

    for el in article_text.find_all('figure'):
      if el.has_attr('class') and 'iframe-container' in el['class']:
        it = el.find('iframe')
        if it and it.has_attr('src'):
          new_html = utils.add_embed(it['src'])
          if el.parent.name == 'div' and el.parent.has_attr('id') and re.search(r'[0-9a-f]{32}', el.parent['id']):
            el = el.parent
          el.insert_after(BeautifulSoup(new_html, 'html.parser'))
          el.decompose()
      else:
        img = el.find('img')
        if img:
          img_src = ''
          if img.has_attr('src'):
            img_src = img.get('src')
          elif img.has_attr('data-wf-src'):
            img_src = img.get('data-wf-src')
          else:
            logger.warning('unknown img src in ' + str(img))

          caption = []
          el_cap = el.find('figcaption')
          if el_cap:
            cap = el_cap.get_text().strip()
            if cap:
              caption.append(cap)
          el_cap = el.find(class_='photo-credit')
          if el_cap:
            cap = el_cap.get_text().strip()
            if cap:
              caption.append(cap)

          img_src = get_full_image(img_src)
          el.insert_after(BeautifulSoup(utils.add_image(img_src, ' | '.join(caption)), 'html.parser'))
          el.decompose()

    for el in article_text.find_all('span', id='end-legacy-contents'):
      el.decompose()

    for el in article_text.find_all(re.compile(r'style|template')):
      el.decompose()

    for el in article_text.find_all('ins'):
      el.unwrap()

    for el in article_text.find_all(attrs={"data-component": "ProductInfo"}):
      el_data = el.find(attrs={"data-component": "ProductScores"})
      if el_data:
        scores_html = '<h2>Scores</h2><ul>'
        for score in el_data.find_all(class_='W(reviewScoreContainerWidth)'):
          scores_html += '<li>{}: {}</li>'.format(score.previous_sibling.get_text(), score.get_text())
        scores_html += '</ul>'
        el.insert_after(BeautifulSoup(scores_html, 'html.parser'))
      el_data = el.find(attrs={"data-component": "ProsCons"})
      if el_data:
        el.insert_after(el_data)
      if el_data:
        el.decompose()

    for el in article_text.find_all('div', id=re.compile(r'[0-9a-f]{32}')):
      it = el.find('iframe')
      if it and it.has_attr('src'):
        new_html = utils.add_embed(it['src'])
        el.insert_after(new_html, 'html.parser')
        el.decompose()

    for el in article_text.find_all('iframe'):
      if el.has_attr('src'):
        new_html = utils.add_embed(el['src'])
        if el.parent.name == 'div' and el.parent.has_attr('id') and re.search(r'[0-9a-f]{32}', el.parent['id']):
          el = el.parent
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()
      else:
        logger.warning('unhandled iframe in ' + url)

    for el in article_text.find_all('blockquote'):
      if el.has_attr('class'):
        new_html = ''
        if 'twitter-tweet' in el['class']:
          tweet_urls = el.find_all('a')
          new_html = utils.add_embed(tweet_urls[-1])
        elif 'instagram-media' in el['class']:
          new_html = utils.add_embed(el['data-instgrm-permalink'])
        else:
          logger.warning('unhandled blockquote class {} in {}'.format(el['class'], url))
        if new_html:
          if el.parent.name == 'div' and el.parent.has_attr('id') and re.search(r'[0-9a-f]{32}', el.parent['id']):
            el = el.parent
          el.insert_after(BeautifulSoup(new_html, 'html.parser'))
          el.decompose()
      else:
        if el.p:
          quote = str(el.p)
          el.insert_after(BeautifulSoup(utils.add_pullquote(quote[3:-4]), 'html.parser'))
          el.decompose()
        else:
          logger.warning('unhandled blockquote in ' + url)

    content_html += str(article_text)

  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)