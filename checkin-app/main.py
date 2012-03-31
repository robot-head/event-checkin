from google.appengine.ext import blobstore
from google.appengine.ext import db
from google.appengine.ext.webapp import blobstore_handlers
import logging
import jinja2
import json
import model
import os
import ticket_file_parser
import webapp2
from django.core.files.uploadhandler import FileUploadHandler


jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))


class TemplateBasedHandler(webapp2.RequestHandler):
  
  template_basepath = 'templates'
  request_template_paths = {
      'get': 'foo.html',
      'post': 'foo_results.html'}
  
  def _GetTemplatePath(self, method):
    return os.path.join(
        self.template_basepath, self.request_template_paths[method])
  
  def _ProcessRequest(self, method, *args, **kwargs):
    template = jinja_environment.get_template(self._GetTemplatePath(method))
    ctx = self.CreateContext(method, *args, **kwargs)
    self.response.out.write(template.render(ctx, *args, **kwargs))
  
  def get(self, *args, **kwargs):
    self._ProcessRequest('get', *args, **kwargs)
  
  def post(self, *args, **kwargs):
    self._ProcessRequest('post', *args, **kwargs)
    
  def CreateContext(self, method, *args, **kwargs):
    """Should return a dictionary with context for the template."""
    return {}


class FileUploadHandler(blobstore_handlers.BlobstoreUploadHandler):
  
  def post(self, event_id):
    event = model.Event.get_by_id(int(event_id))
    upload_files = self.get_uploads('file')
    reader = blobstore.BlobReader(upload_files[0])
    parser = ticket_file_parser.CsvTicketFileParser(reader, event)
    parser.key_position = 5
    parser.Parse()
    self.redirect('/event/%s' % event_id)


class TicketUnmarkHandler(TemplateBasedHandler):
  
  request_template_paths = {
      'post': 'ticket_unmark_results.html'}
  
  def DecrementClaimCount(self):
    def transaction():
      new_count = self.ticket.claim_count - 1
      log = model.EventLog(
          old_count=self.ticket.claim_count, new_count=new_count,
          ticket=self.ticket, event=self.event)
      log.put()
      self.ticket.claim_count -= 1
      self.ticket.put()
    """
    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, transaction)
    """
    transaction()

  def GetTicket(self, code):
    query = db.Query(model.Ticket)
    query.filter('code =', code)
    query.filter('event =', self.event)
    if (query.count() != 1):
      raise self.TicketFindError(
          '%d tickets found instead of 1 for code %s' % (query.count(), code))
    return query.get()

  def GetLog(self):
    log_query = db.Query(model.EventLog)
    log_query.filter('event = ', self.event)
    log_query.filter('ticket =', self.ticket)
    log_query.order('timestamp')
    return log_query.fetch(100)
    
  def CreateContext(self, method, event_id):
    code = self.request.get('code')
    self.event = model.Event.get_by_id(int(event_id))
    error = None
    try:
      self.ticket = self.GetTicket(code)
    except self.TicketFindError, e:
      error = str(e)
      return {
        'error': error,
        'log': None,
        'event': self.event,
        'ticket': None}
    headers = json.loads(self.event.descriptor_format)
    descriptor = json.loads(self.ticket.descriptor)
    self.DecrementClaimCount()
    log = self.GetLog()
    return {
        'error': error,
        'log': log,
        'event': self.event,
        'ticket': self.ticket,
        'headers': headers,
        'descriptor': descriptor}
    
class TicketMarkHandler(TemplateBasedHandler):
  
  request_template_paths = {
      'post': 'ticket_mark_results.html'}
  
  class Error(Exception): pass
  class TicketValidationError(Error): pass
  class TicketFindError(Error): pass

  def ValidateTicket(self, force_checkin=False):
    if self.ticket.claim_count > 0:
      if not force_checkin:
        raise self.TicketValidationError('Ticket already claimed')
  
  def IncrementClaimCount(self):
    def transaction():
      new_count = self.ticket.claim_count + 1
      log = model.EventLog(
          old_count=self.ticket.claim_count, new_count=new_count,
          ticket=self.ticket, event=self.event)
      log.put()
      self.ticket.claim_count += 1
      self.ticket.put()
    """
    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, transaction)
    """
    transaction()
    
  def GetTicket(self, code):
    query = db.Query(model.Ticket)
    query.filter('code =', code)
    query.filter('event =', self.event)
    if (query.count() != 1):
      raise self.TicketFindError(
          '%d tickets found instead of 1 for code %s' % (query.count(), code))
    return query.get()

  def GetLog(self):
    log_query = db.Query(model.EventLog)
    log_query.filter('event = ', self.event)
    log_query.filter('ticket =', self.ticket)
    log_query.order('timestamp')
    return log_query.fetch(100)
    
  def CreateContext(self, method, event_id):
    code = self.request.get('code')
    force_checkin = self.request.get('force')
    self.event = model.Event.get_by_id(int(event_id))
    logging.info('%s and %s', self.event, code)
    error = None
    try:
      self.ticket = self.GetTicket(code)
    except self.TicketFindError, e:
      error = str(e)
      return {
        'error': error,
        'log': None,
        'event': self.event,
        'ticket': None}
    headers = json.loads(self.event.descriptor_format)
    descriptor = json.loads(self.ticket.descriptor)
    try:
      self.ValidateTicket(force_checkin)
    except self.TicketValidationError, e:
      error = str(e)
      log = self.GetLog()
      return {
          'error': error,
          'log': log,
          'event': self.event,
          'ticket': self.ticket,
          'headers': headers,
          'descriptor': descriptor}
    self.IncrementClaimCount()
    log = self.GetLog()
    return {
        'error': error,
        'log': log,
        'event': self.event,
        'ticket': self.ticket,
        'headers': headers,
        'descriptor': descriptor}


class EventMainPage(TemplateBasedHandler):
  
  request_template_paths = {
      'get': 'event_index.html'}
  

  def GetNumberOfTicketsWithScans(self, event, count):
    query = db.Query(model.Ticket)
    query.filter('claim_count =', count)
    query.filter('event =', event)
    tickets = query.count()
    return tickets

  def CreateContext(self, method, event_id):
    event = model.Event.get_by_id(int(event_id))
    ticket_query = db.Query(model.Ticket)
    ticket_query.filter('event =', event)
    num_tickets = ticket_query.count()
    first_10_tickets = ticket_query.fetch(limit=10)
    ticket_count_map = {}
    upload_url = blobstore.create_upload_url('/event/upload/%s' % event_id)
    for count in [0, 1]:
      tickets = self.GetNumberOfTicketsWithScans(event, count)
      ticket_count_map[str(count)] = tickets
    query = db.Query(model.Ticket)
    query.filter('claim_count >', 1)
    query.filter('event =', event)
    ticket_count_map['>1'] = query.count()
    return {
        'event': event,
        'tickets': first_10_tickets,
        'num_tickets': num_tickets,
        'ticket_state_map': ticket_count_map,
        'upload_url': upload_url
        }


class EventCreationHandler(webapp2.RequestHandler):
  
  def post(self):
    event_name = self.request.get('name')
    if event_name:
      event = model.Event(name=event_name)
      event.put()
      return webapp2.redirect_to('event', event_id = event.key().id())


class MainPage(TemplateBasedHandler):
  
  def CreateContext(self, method):
    event_list = model.Event.all()
    return {
        'events': event_list }
  
  request_template_paths = {
      'get': 'index.html'}


app = webapp2.WSGIApplication([
    webapp2.Route(r'/', handler=MainPage, name='home'),
    webapp2.Route(
        r'/event/<event_id:\d+>', handler=EventMainPage, name='event'),
    webapp2.Route(
        r'/event/upload/<event_id:\d+>', handler=FileUploadHandler,
        name='upload'),
    webapp2.Route(
        r'/event/<event_id:\d+>/ticket/mark',
        handler=TicketMarkHandler, name='mark'),
     webapp2.Route(
        r'/event/<event_id:\d+>/ticket/unmark',
        handler=TicketUnmarkHandler, name='unmark'),
    webapp2.Route(
        r'/event/new', handler=EventCreationHandler, name='create_event')],
    debug=True)