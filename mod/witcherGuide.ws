// Witcher Guide companion mod.
// Reports journalQuest state to the script log so the overlay can follow the game.
// Output only appears when the game is launched with -debugscripts.
// Message format: see mod/README.md in the overlay repository.
//
// The calls below were copied from how the game's own scripts use the journal
// (game/journal.ws, game/gui/menus/questListMenu.ws, game/gui/hud/hud.ws).

function WG_StatusName( status : EJournalStatus ) : string
{
	if ( status == JS_Success )
	{
		return "success";
	}
	if ( status == JS_Failed )
	{
		return "failed";
	}
	if ( status == JS_Active )
	{
		return "active";
	}
	return "inactive";
}

function WG_QuestTitle( journalQuest : CJournalQuest ) : string
{
	return GetLocStringById( journalQuest.GetTitleStringId() );
}

function WG_LogTracked( journalQuest : CJournalQuest )
{
	if ( journalQuest )
	{
		LogChannel( 'modWG', "@@WG@@|tracked|" + WG_QuestTitle( journalQuest ) );
	}
	else
	{
		LogChannel( 'modWG', "@@WG@@|tracked|" );
	}
}

// Writes the state of every journalQuest in the journal, then the tracked journalQuest.
function WG_Snapshot()
{
	var manager : CWitcherJournalManager;
	var entries : array< CJournalBase >;
	var journalQuest : CJournalQuest;
	var i : int;

	manager = theGame.GetJournalManager();
	if ( !manager )
	{
		return;
	}

	manager.GetActivatedOfType( 'CJournalQuest', entries );
	if ( entries.Size() == 0 )
	{
		return;
	}

	LogChannel( 'modWG', "@@WG@@|snapshot|begin" );
	for ( i = 0; i < entries.Size(); i += 1 )
	{
		journalQuest = ( CJournalQuest )entries[i];
		if ( journalQuest )
		{
			LogChannel( 'modWG', "@@WG@@|q|" + WG_QuestTitle( journalQuest ) + "|" + WG_StatusName( manager.GetEntryStatus( journalQuest ) ) );
		}
	}
	LogChannel( 'modWG', "@@WG@@|snapshot|end" );

	WG_LogTracked( manager.GetTrackedQuest() );
}
