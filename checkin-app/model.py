from google.appengine.ext import db

class Event(db.Model):
  name = db.StringProperty(required=True)
  # Header row for the dynamic data on each ticket
  descriptor_format = db.StringProperty()
  
  def __unicode__(self):
    return self.name

class Ticket(db.Model):
  code = db.StringProperty(required=True)
  # Comma seperated dynamic data can go here
  descriptor = db.StringProperty()
  event = db.ReferenceProperty(Event)
  claim_count = db.IntegerProperty(default=0)


class EventLog(db.Model):
  old_count = db.IntegerProperty(required=True)
  new_count = db.IntegerProperty(required=True)
  ticket = db.ReferenceProperty(Ticket)
  # Denormalized for quick indexing
  event = db.ReferenceProperty(Event)
  timestamp = db.DateTimeProperty(auto_now=True)