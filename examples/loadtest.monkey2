'Houdini scene to mojo3d demostration
'Try changing the scene in houdini, re-export it and hit space bar in this app. The changes will reload, without the need to recompile!

Namespace myapp3d

#Import "<std>"
#Import "<mojo>"
#Import "<mojo3d>"
#Import "<mojo3d-loaders>"
#Import "source/mojomesh"

#Import "models/"
#Import "textures/"
#Import "scenes/"
#Import "scenes/meshes/"

#Reflect mojo3d
#Reflect mojogame

Using std..
Using mojo..
Using mojo3d..
Using mojogame..

Class MyWindow Extends Window
	
	Const flags := WindowFlags.Resizable' | WindowFlags.HighDPI
	
	'in oder to try hot-reloading, point this to your absolute local path, i.e. "/pathtofile/scenes/testscene.mojo3d"
	Field path := "asset::basicscene.mojo3d" 
	Field _scene:Scene
	Field _camera:Camera
	

	Method New( title:String="Simple mojo3d loader",width:Int=1280,height:Int=720 )
		Super.New( title,width,height,flags )
	End
	
	
	Method OnCreateWindow() Override
		ReloadScene()
		_scene.AddPostEffect( New FXAAEffect )
	End
	
	
	Method OnRender( canvas:Canvas ) Override
		RequestRender()
		_scene.Update()
		_camera.Render( canvas )
		canvas.DrawText( "FPS="+App.FPS,5,5 )
		canvas.DrawText( "Hit space bar to reload the scene - No need to recompile to see changes to the .mojo3d file!", 5, Height-5, 0, 1 )
		
		If Keyboard.KeyHit( Key.Space ) Then ReloadScene()
	End
	
	
	Method ReloadScene()
		_scene = _scene.Load( path )
		_camera = FindCamera( _scene.GetRootEntities() )
		_camera.View = Self
		_camera.AddComponent<FlyBehaviour>()
		Print "Scene reloaded"
	End
	
End


Function Main()
	New AppInstance
	New MyWindow
	App.Run()
End



Function FindCamera:Camera( entities:Entity[] )
	Local cam:Camera
	For Local e:= Eachin entities
		Local candidate := Cast<Camera>( e )
		If candidate
			Print "Scene: Camera named '" + candidate.Name + "' Found"
			Return candidate
		Else
			cam = FindCamera( e.Children )
		End
	Next
	Return cam
End
	




































