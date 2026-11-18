// Witcher Guide companion mod.
// Reports quest state to the script log so the overlay can follow the game.
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

function WG_QuestTitle( quest : CJournalQuest ) : string
{
	return GetLocStringById( quest.GetTitleStringId() );
}

function WG_LogTracked( quest : CJournalQuest )
{
	if ( quest )
	{
		LogChannel( 'modWG', "@@WG@@|tracked|" + WG_QuestTitle( quest ) );
	}
	else
	{
		LogChannel( 'modWG', "@@WG@@|tracked|" );
	}
}

// Writes the state of every quest in the journal, then the tracked quest.
function WG_Snapshot()
{
	var manager : CWitcherJournalManager;
	var entries : array< CJournalBase >;
	var quest : CJournalQuest;
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
		quest = ( CJournalQuest )entries[i];
		if ( quest )
		{
			LogChannel( 'modWG', "@@WG@@|q|" + WG_QuestTitle( quest ) + "|" + WG_StatusName( manager.GetEntryStatus( quest ) ) );
		}
	}
	LogChannel( 'modWG', "@@WG@@|snapshot|end" );

	WG_LogTracked( manager.GetTrackedQuest() );
}
