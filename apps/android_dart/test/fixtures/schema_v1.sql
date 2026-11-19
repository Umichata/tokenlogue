-- Exact CREATE statements from the first Dart schema.
CREATE TABLE profile(id TEXT PRIMARY KEY NOT NULL);
CREATE TABLE preferences(name TEXT PRIMARY KEY NOT NULL,value TEXT NOT NULL);
CREATE TABLE chats(id TEXT PRIMARY KEY NOT NULL, title BLOB NOT NULL,title_rev INTEGER NOT NULL, provider TEXT NOT NULL CHECK(provider IN ("openrouter","vsegpt")),model TEXT NOT NULL,free INTEGER NOT NULL,created INTEGER NOT NULL,token_limit INTEGER,skip_paid INTEGER NOT NULL DEFAULT 0,connection_rev INTEGER NOT NULL DEFAULT 1);
CREATE TABLE drafts(chat TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,rev INTEGER NOT NULL CHECK(rev>0),body BLOB NOT NULL);
CREATE TABLE budgets(chat TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,provider TEXT NOT NULL,currency TEXT NOT NULL,amount TEXT,PRIMARY KEY(chat,provider,currency));
CREATE TABLE turns(id TEXT PRIMARY KEY NOT NULL,chat TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,created INTEGER NOT NULL);
CREATE TABLE messages(id TEXT PRIMARY KEY NOT NULL,turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,role TEXT NOT NULL CHECK(role IN ("user","assistant")),body BLOB NOT NULL,ordinal INTEGER NOT NULL,UNIQUE(turn_id,role));
CREATE TABLE attempts(id TEXT PRIMARY KEY NOT NULL,turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,provider TEXT NOT NULL,currency TEXT NOT NULL,requested_model TEXT NOT NULL,actual_model TEXT,dispatch_ms INTEGER,state TEXT NOT NULL,reserved_tokens INTEGER NOT NULL,reserved_cost TEXT,usage_in INTEGER,usage_out INTEGER,usage_total INTEGER,usage_source TEXT,cost TEXT,cost_source TEXT,snapshot BLOB NOT NULL);
CREATE INDEX attempts_time ON attempts(dispatch_ms);
