Namespace myapp3d

#Import "<std>"
#Import "<mojo>"
#Import "<mojo3d>"
#Import "<mojo3d-loaders>"

#Import "models/"
#Import "textures/"
#Import "scenes/"

#Reflect mojo3d

Using std..
Using mojo..
Using mojo3d..


Class MyWindow Extends Window
	
	Field _scene:Scene
	Field _camera:Camera
	
	Method New( title:String="Simple mojo3d app",width:Int=640,height:Int=480,flags:WindowFlags=WindowFlags.Resizable )
		Super.New( title,width,height,flags )
	End
	
	
	Method OnCreateWindow() Override
		_scene = _scene.Load( "asset::test.mojo3d" )
		_camera = Cast<Camera>(_scene.FindEntity("Camera") )
		_camera.View = Self
		_camera.AddComponent<FlyBehaviour>()
	End
	
	
	Method OnRender( canvas:Canvas ) Override
		RequestRender()
		_scene.Update()
		_camera.Render( canvas )
		canvas.DrawText( "FPS="+App.FPS,0,0 )
	End
	
End

Function Main()
	New AppInstance
	New MyWindow
	App.Run()
End
