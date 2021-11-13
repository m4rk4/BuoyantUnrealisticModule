import json, re
from bs4 import BeautifulSoup
from datetime import datetime

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  if url.endswith('/'):
    json_url = url[:-1] + '.json'
  else:
    json_url = url + '.json'
  article_json = utils.get_url_json(json_url)
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  page = article_json['config']['page']

  item = {}
  item['id'] = page['pageId'] 
  item['url'] = url
  item['title'] = page['headline']

  dt = datetime.fromtimestamp(int(page['webPublicationDate'])/1000)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  if page.get('author'):
    item['author']['name'] = page['author']
  elif page.get('byline'):
    item['author']['name'] = page['byline']
  else:
    item['author']['name'] = 'The Guardian'
  item['tags'] = page['keywords'].split(',')
  item['_image'] = page['thumbnail']

  content_html = ''
  article_body = None

  article_html = article_json['html'].replace('<p>***</p>', '<hr width="80%" />')
  soup = BeautifulSoup(article_html, 'html.parser')
  if save_debug:
    utils.write_file(article_json['html'], './debug/debug.html')

  def get_lightbox_image(image_id):
    nonlocal page
    nonlocal url
    img_src = ''
    if not page.get('lightboxImages'):
      return img_src, ''
    if not page['lightboxImages'].get('images'):
      return img_src, ''
    if not image_id:
      image = page['lightboxImages']['images'][0]
    else:
      m = False
      for image in page['lightboxImages']['images']:
        if image_id in image['src']:
          m = True
          break
      if not m:
        logger.warning('no match found for image {} in {}'.format(image_id, url))
    images = []
    for src in image['srcsets'].split(','):
      m = re.search(r'([^\s]+)\s(\d+)w', src)
      if m:
        img = {}
        img['src'] = m.group(1)
        img['width'] = int(m.group(2))
        images.append(img)
    img = utils.closest_dict(images, 'width', 1000)
    img_src = img['src']
    caption = []
    if image.get('caption'):
      caption.append(image['caption'].strip())
    if image.get('credit'):
      caption.append(image['credit'])
    return img['src'], ' | '.join(caption)

  def replace_image(el_image):
    img_src = ''
    if el_image.get('data-media-id'):
      img_src, caption = get_lightbox_image(el_image['data-media-id'])
    if not img_src:
      logger.debug('image not found in lightboxImages')
      images = []
      for el in el_image.find_all('source'):
        if el.get('srcset'):
          for src in el['srcset'].split(','):
            m = re.search(r'([^\s]+)\s(\d+)w', src)
            if m:
              image = {}
              image['url'] = m.group(1)
              image['width'] = int(m.group(2))
              images.append(image)
      if images:
        image = utils.closest_dict(images, 'width', 1000)
        img_src = image['url']
      else:
        el = el_image.find('meta', attrs={"itemprop": "url"})
        if el:
          img_src = el['content']
        else:
          img = el_image.find('img')
          img_src = el['src']
      caption = ''
      el = el_image.find('figcaption')
      if el:
        caption = el.get_text()
    el_image.insert_after(BeautifulSoup(utils.add_image(img_src, caption), 'html.parser'))
    el_image.decompose()

  if '/video/' in url:
    el = soup.find(class_='youtube-media-atom__iframe')
    if el:
      content_html += utils.add_video('https://www.youtube.com/embed/' + el['data-asset-id'], 'youtube')
    el = soup.find(class_='content__standfirst')
    if el:
      if el.meta:
        item['summary'] = el.meta['content']
      content_html += str(el)
    if content_html:
      item['content_html'] = content_html
      return item

  elif '/audio/' in url:
    el = soup.find('img', class_='podcast__cover-image')
    if el:
      content_html += utils.add_image(el['src'])
    el = soup.find(class_='podcast__meta-item--download')
    if el:
      content_html += '<audio controls><source src="{0}" type="audio/mpeg">Your browser does not support the audio element.</audio><br /><a href="{0}"><small>Play audio</small></a>'.format(el.a['href'])
    el = soup.find(class_='content__standfirst')
    if el:
      if el.meta:
        item['summary'] = el.meta['content']
      it = el.find('a', attrs={"data-component": "podcast-help"})
      if it:
        #it.parent.insert_after(BeautifulSoup('<hr>', 'html.parser'))
        it.parent.decompose()
      content_html += str(el) + '<hr>'
    article_body = soup.find(class_='podcast__body')
    #content_html += article_json['html']

  else:
    if page.get('lightboxImages'):
      item['summary'] = page['lightboxImages']['standfirst']
      img_src, caption = get_lightbox_image('')
      if img_src:
        content_html += utils.add_image(img_src, caption)

    el = soup.find('figure', class_='element-atom--main-media')
    if el:
      it = el.find(class_='youtube-media-atom__iframe')
      if it:
        fig_caption = el.find('figcaption')
        if fig_caption:
          caption = fig_caption.get_text()
        else:
          caption = None
        content_html += utils.add_youtube(it['data-asset-id'], caption=caption)
      else:
        logger.warning('unhandled element-atom--main-media in ' + url)

    # add rating (for reviews)
    el = soup.find(attrs={"itemprop": "reviewRating"})
    if el:
      content_html += '<h4>Rating: {}</h4>'.format(el.get_text())

    article_body = soup.find(class_='content__article-body')

  if article_body:
    for el in article_body.find_all('figure', class_='element-image'):
      replace_image(el)

    for el in article_body.find_all('figure', attrs={"itemprop": re.compile(r'\bimage\b')}):
      replace_image(el)

    for el in article_body.find_all('figure', class_='element-video'):
      if el.get('data-canonical-url') and 'youtube' in el['data-canonical-url']:
        new_el = BeautifulSoup(utils.add_embed(el['data-canonical-url']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in article_body.find_all('figure', class_='element-atom'):
      if el['data-atom-type'] == 'media':
        it = el.find(class_='youtube-media-atom__iframe')
        if it:
          fig_caption = el.find('figcaption')
          if fig_caption:
            caption = fig_caption.get_text()
          else:
            caption = None
          new_el = BeautifulSoup(utils.add_youtube(it['data-asset-id'], caption=caption), 'html.parser')
          el.insert_after(new_el)
          el.decompose()
        else:
          logger.warning('unhandled element-atom media type {} in {}'.format(el['data-atom-type'], url))
      elif el['data-atom-type'] == 'guide' or el['data-atom-type'] == 'qanda':
        snippet_head = '<h4>'
        it = el.find(class_='atom--snippet__label')
        if it:
          snippet_head += '{}: '.format(it.string)
        it = el.find(class_='atom--snippet__headline')
        if it:
          snippet_head += it.string
        snippet_head += '</h4>'
        snippet_body = el.find(class_='atom--snippet__body')
        if snippet_body:
          snippet_body.name = 'blockquote'
          snippet_body['style'] = 'padding-left:1em; padding-right:1em; border:2px solid black; background-color:lightgrey;'
          snippet_body.insert(0, BeautifulSoup(snippet_head, 'html.parser'))
          img = snippet_body.find('img')
          if img:
            img.decompose()
          el.insert_after(snippet_body)
          el.decompose()

    for el in article_body.find_all('figure', class_='element-tweet'):
      tweet = utils.add_twitter(el['data-canonical-url'])
      if tweet:
        new_el = BeautifulSoup(tweet, 'html.parser')
        el.insert_after(new_el)
        el.decompose()
      else:
        logger.warning('unable to add tweet {} in {}'.format(el['data-canonical-url'], url))

    for el in article_body.find_all('figure', class_='element-embed'):
      if el.iframe:
        if 'email-sub__iframe' in el.iframe['class']:
          el.decompose()
        else:
          if el.iframe.get('srcdoc'):
            embed_src = ''
            srcdoc = BeautifulSoup(el.iframe['srcdoc'], 'html.parser')
            if srcdoc.blockquote:
              if srcdoc.blockquote.get('data-instgrm-permalink'):
                embed_src = srcdoc.blockquote['data-instgrm-permalink']
              elif 'tiktok-embed' in srcdoc.blockquote['class']:
                embed_src = srcdoc.blockquote['cite']
            if embed_src:
              new_el = BeautifulSoup(utils.add_embed(embed_src), 'html.parser')
              el.insert_after(new_el)
              el.decompose()
            else:
              logger.warning('unknown iframe type in ' + url)
      else:
        logger.warning('no iframe in element-embed in ' + url)
  
    for el in article_body.find_all('figure', class_='element-interactive'):
      if not 'sign-up' in str(el):
        new_el = BeautifulSoup('<iframe width="640px" height="480px" frameBorder="0" src={}></iframe'.format(el['data-canonical-url']), 'html.parser')
        el.insert_after(new_el)
      el.decompose()

    for el in article_body.find_all('aside', class_='element-pullquote'):
      author = ''
      it = el.find('cite')
      if it:
        author = it.get_text().strip()
        it.decompose()
      quote = el.blockquote.p.get_text()
      new_el = BeautifulSoup(utils.add_pullquote(quote, author), 'html.parser')
      el.insert_after(new_el)
      el.decompose()

    for el in article_body.find_all('aside', class_='element-rich-link'):
      if el.find(class_='rich-link__read-more-text'):
        el.decompose()

    for el in article_body.find_all('span', class_='drop-cap'):
      new_html = '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>'.format(el.get_text())
      new_el = BeautifulSoup(new_html, 'html.parser')
      el.insert_after(new_el)
      new_el = BeautifulSoup('<div style="clear:left;"></div>', 'html.parser')
      el.parent.insert_after(new_el)
      el.decompose()

    content_html += str(article_body)
  else:
    content_html += article_json['html']

  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)