
# To do:
# Auto-convert maps to pbr material if color texture path contains ".pbr"
# Multiple materials per model (maybe using multiple material nodes inside geo?)
# Object merge to an object in the same hierarchy causes endless loop in the mojo3d side, needs warning
# Explore massive instancing (CopyToPoints, etc.). May need custom components in mojo3d.

#----------------------------------------------------------------------------

import json
import math

jsondict = dict()       #main json file
orderedNodes = []       #final list, contains one json dictionary per valid node in the correct order

uniqueIDCounter = -1

root = hou.node("/obj")

convertLoadersToGlb = False
convertSaversToGlb = False
convertAssetPaths = False

#-------------------------------- Classes ----------------------------------

class mojonode:
        byHounode = dict()
        byPriority = dict()
        byReference = dict()    #Keys: all path references, to be replaced by mojo ids, Values:the correspondent mojonode
        byAssetPath = dict()    #kind of a pain, Houdini has no texture nodes.... key:asset path, value:mojonode

        uniqueIDCounter = 0                    #provides an index for references (i.e. textures) before mojoID numbers are assigned

        def __init__( self, node, decl, decltype, args, argtypes, returntype, priority ):
                global uniqueIDCounter

                self.json = dict()
                self.node = node
                self.mojoID = None
                self.byHounode[node] = self

                uniqueIDCounter += 1
                self.uniqueID = "uniqueID<" + str(uniqueIDCounter) + ">"
                self.byReference[self.uniqueID] = self

                if not priority in self.byPriority.keys(): self.byPriority[priority] = []
                self.byPriority[priority].append( self )

                self.json["ctor"] ={"decl":decl,"args":args,"type": returntype+"("+listToString(argtypes)+")"}
                self.json["type"] = decltype
                self.json["state"] = dict()

class flags:
        normal = 12
        cube = 516
        cubeMip = 524
        env = 1028
        envMip = 1036


#-------------------------------- Utilities ----------------------------------


def compact( t ):
        result = ""
        isArray = False
        for n in range(0, len(t)):
                char = t[n]
                if char == "[":
                        isArray = True
                if char == "]":
                        isArray = False
                if ( char == "\n" or char == " " ):
                        if isArray:
                                char = ""       
                if char == ",":
                        char = ", "
                result += char
                previous = n
        result = result.replace( ", ", ",")
        return result


def listToString( l ):
        text = ""
        for s in l:
                text += s
                text += ","
        text = text[:-1]
        return text


def mojomatrix( n ):
        values = dict()
        values["translate"] = ( n.parm("tx").eval(), n.parm("ty").eval(), n.parm("tz").eval() * -1 )
        values["rotate"] = ( n.parm("rx").eval()*-1, n.parm("ry").eval() *-1, n.parm("rz").eval() )
        values["scale"] = ( n.parm("sx").eval(), n.parm("sy").eval(), n.parm("sz").eval() )

        xform = hou.hmath.buildTransform( values )
        localmtx = xform.asTuple()

        mojomtx = list()
        c = 1
        for e in localmtx:
                if c % 4 != 0:  #skip every fourth number
                        mojomtx.append(e)
                c += 1
        return mojomtx


def eval(n,p):
        return n.parm(p).eval()

#-------------------------------- Mojo Translators ----------------------------------


def buildtree( n, transformParent = None ):
        if not n.isDisplayFlagSet(): return
        getentity( n, transformParent )
        for o in n.outputs():
                buildtree( o )


def getentity( n, transformParent = None ):

        parent = getparent(n, transformParent)
        # parent = getparent(n)

        if n.type().name() == ("subnet"):
                entity = mojonode( n, "mojo3d.Pivot.New", "mojo3d.Pivot", [parent], ["mojo3d.Entity"], "Void", 4 )
                for c in n.children():
                        inputs = c.inputs()
                        if( not inputs ) or (n.inputs()[0] in inputs):
                                buildtree( c, n )
        else:
                #detect reference to existing mojo model load
                mpath = getModelPath(n)
                modelpath = ""
                filemode = ""
                if mpath:
                        modelpath = mpath[0]
                        filemode = mpath[1]
                if modelpath:
                        if modelpath in mojonode.byAssetPath.keys():
                                #reference to file already exists, instance it
                                model = mojonode.byAssetPath[modelpath]
                                entity = mojonode( n, "mojo3d.Entity.Copy", "mojo3d.Entity", [parent], ["mojo3d.Entity"], "mojo3d.Entity", 5 )
                                entity.json["ctor"]["inst"] = model.uniqueID
                                assignMaterial(n)
                        else:
                                if filemode == "read" and not collapseHierachyOnLoad:
                                        entity = mojonode( n, "mojo3d.Model.LoadBoned", "mojo3d.Model", [modelpath], ["String"], "mojo3d.Model", 5 )
                                else:
                                        entity = mojonode( n, "mojo3d.Model.Load", "mojo3d.Model", [modelpath], ["String"], "mojo3d.Model", 5 )
                                mojonode.byAssetPath[modelpath] = entity
                                mojonode.byHounode[n].json["state"]["Parent"] = parent
                                assignMaterial(n)


                elif n.type().name().startswith("geo"):
                        if n.children():
                                mergeobj = getobjmerge(n)
                                if mergeobj:
                                        if mojonode.byHounode[mergeobj]:
                                                entity = mojonode( n, "mojo3d.Entity.Copy", "mojo3d.Entity", [parent], ["mojo3d.Entity"], "mojo3d.Entity", 5 )
                                                entity.json["ctor"]["inst"] = mojonode.byHounode[mergeobj].uniqueID
                                                assignMaterial(n)
                                else:
                                        args = [getmesh(n),getmaterial(n),parent]
                                        argtypes = ["mojo3d.Mesh","mojo3d.Material","mojo3d.Entity"]
                                        entity = mojonode( n, "mojo3d.Model.New", "mojo3d.Model", args, argtypes, "Void", 4 )
                                        color = getcolornode(n)
                                        if color: mojonode.byHounode[n].json["state"]["Color"] = color
                        else:
                                args = [parent]
                                argtypes = ["mojo3d.Entity"]
                                entity = mojonode( n, "mojo3d.Pivot.New", "mojo3d.Pivot", args, argtypes, "Void", 4 )

                elif n.type().name().startswith("hlight"):
                        if not n.parm("light_enable").eval(): return
                        if not n.parm("ogl_enablelight").eval(): return

                        args = [parent]
                        argtypes = ["mojo3d.Entity"]
                        entity = mojonode( n, "mojo3d.Light.New", "mojo3d.Light", args, argtypes, "Void", 4 )
                        mojolight = 1
                        if n.parm("light_type").eval() == 0: mojolight = 2
                        if n.parm("coneenable").eval() == 1: mojolight = 3
                        if n.parm("light_type").eval() >= 7: mojolight = 1
                        mojoshadow = 0
                        if n.parm("shadow_type").eval() > 0: mojoshadow = 1
                        atten_type = n.parm("atten_type").eval()
                        mojorange = 100.0
                        if atten_type == 0: mojorange = 10000.0                                                 #virtually no attentuation
                        elif atten_type == 1: mojorange = n.parm("atten_dist").eval() * 25.0                    #not correct at all...
                        else: hou.ui.displayMessage( "Export Warning: unsupported light attentuation type" )    #inverse square, not implemented in mojo yet?

                        mojonode.byHounode[n].json["state"]["Color"] = getcolor(n,"light_color",1.0,n.parm("light_intensity").eval())
                        mojonode.byHounode[n].json["state"]["Type"] = mojolight
                        mojonode.byHounode[n].json["state"]["CastsShadow"] = mojoshadow
                        mojonode.byHounode[n].json["state"]["Range"] = mojorange
                        mojonode.byHounode[n].json["state"]["OuterAngle"] = (n.parm("coneangle").eval()/2.0) + n.parm("conedelta").eval()
                        mojonode.byHounode[n].json["state"]["InnerAngle"] = n.parm("coneangle").eval()/2.0

                elif n.type().name().startswith("cam"):
                        args = [parent]
                        argtypes = ["mojo3d.Entity"]
                        entity = mojonode( n, "mojo3d.Camera.New", "mojo3d.Camera", args, argtypes, "Void", 4 )
                        mojonode.byHounode[n].json["state"]["Near"] = n.parm("near").eval()
                        mojonode.byHounode[n].json["state"]["Far"] = n.parm("far").eval()
                        mojonode.byHounode[n].json["state"]["FOV"] = 2.0 * math.degrees( math.atan ( ( ( (n.parm("resy").eval()*n.parm("aperture").eval() ) / (n.parm("resx").eval() ) )/2.0) / n.parm("focal").eval() ) )

                elif n.type().name().startswith("envlight"):
                        mojonode.byHounode[root].json["state"]["EnvColor"] = getcolor(n, "light_color", 1.0 )
                        mojonode.byHounode[root].json["state"]["EnvTexture"] = gettexture(n, "env_map", flags.envMip )
                        mojonode.byHounode[root].json["state"]["SkyTexture"] = gettexture(n, "env_map", flags.envMip )
                        return
                
                elif n.type().name().startswith("ambient"):
                        mojonode.byHounode[root].json["state"]["AmbientLight"] = getcolor(n, "light_color", 1.0, 1.0)
                        return
                else:
                        print "Not a valid Mojo3D node:", n.type().name(), n.name()
                        return

        #Basic Entity states
        mojonode.byHounode[n].json["state"]["Name"] = n.name()
        mojonode.byHounode[n].json["state"]["LocalMatrix"] = mojomatrix( n )

        
def getparent(n, transformParent=None):
        if transformParent:
                parent = mojonode.byHounode[transformParent]
                return parent.uniqueID
        if len(n.inputs()) == 1:
                parent = mojonode.byHounode[n.inputs()[0]]
                return parent.uniqueID
        else:
                return None


def getcolor(n,pname,alpha = 1.0, multiplier = 1.0):
        return [math.pow(n.parm(pname+"r").eval()*multiplier, 1/2.2),
                math.pow(n.parm(pname+"g").eval()*multiplier, 1/2.2),
                math.pow(n.parm(pname+"b").eval()*multiplier, 1/2.2),
                alpha ]


def getcolornode(n):
        for c in n.children():
                if c.isBypassed(): return None
                if c.type().name() == "color":
                        return getcolor(c,"color")
        return None

def getobjmerge(n):
        for c in n.children():
                if c.isBypassed(): return None
                if c.type().name() == "object_merge":
                        objpath = c.parm("objpath1").eval()
                        if objpath:
                                print "################# ", objpath, "################# "
                                return hou.node( objpath )
        return None


def getbox(n,pname):
        x=n.parm(pname+"x").eval()
        y=n.parm(pname+"y").eval()
        z=n.parm(pname+"z").eval()
        tx=n.parm("tx").eval()
        ty=n.parm("ty").eval()
        tz=n.parm("tz").eval()
        return [ (-x/2.0)+tx,(-y/2.0)+ty, (-z/2.0)+tz, (x/2.0)+tx, (y/2.0)+ty, (z/2.0)+tz ]
        

def getmaterial(n):
        if n.parm( "shop_materialpath"):
                matpath = n.parm( "shop_materialpath").eval()
                matnode = hou.node( matpath )
                if matnode:
                        #Build material node, if doesn't exist already
                        if not matnode in mojonode.byHounode.keys():
                                args = [ getcolor(matnode,"basecolor",1.0), matnode.parm("metallic").eval(), matnode.parm("rough").eval() ]
                                argtypes = ["std.graphics.Color","Float","Float"]
                                mat = mojonode( matnode, "mojo3d.PbrMaterial.New", "mojo3d.PbrMaterial", args, argtypes, "Void", 2 )
                                if eval(n,"basecolor_texture"):mat.json["state"]["ColorTexture"] = gettexture(n,"basecolor_texture")
                                if eval(n,"rough_texture"):mat.json["state"]["RoughnessTexture"] = gettexture(n,"rough_texture")
                                if eval(n,"metallic_texture"):mat.json["state"]["MetalnessTexture"] = gettexture(n,"metallic_texture")
                                if eval(n,"emitcolor_texture"):mat.json["state"]["EmissiveTexture"] = gettexture(n,"emitcolor_texture")
                                if eval(n,"baseNormal_texture"):mat.json["state"]["NormalTexture"] = gettexture(n,"baseNormal_texture")
                                return mat.uniqueID
                        else:
                                return mojonode.byHounode[ matnode ].uniqueID
                else:
                        # hou.ui.displayMessage( "Mojo Exporter Warning: Entity " + n.name() + " has no material!")
                        if "DefaultMaterial" in mojonode.byAssetPath.keys():
                                return mojonode.byAssetPath["DefaultMaterial"].uniqueID
                        else:
                                args = [ [0.7, 0.7, 0.7, 1.0], 0.0, 0.5 ]
                                argtypes = ["std.graphics.Color","Float","Float"]
                                mat = mojonode( None, "mojo3d.PbrMaterial.New", "mojo3d.PbrMaterial", args, argtypes, "Void", 2 )
                                mojonode.byAssetPath["DefaultMaterial"] = mat
                                return mat.uniqueID
                        # return None
                

def getmesh(n):
        for c in n.children():
                if c.isBypassed(): return None
                name = c.type().name()
                if name == "grid":
                        width = c.parm("sizex").eval()
                        height = c.parm("sizey").eval()
                        args = [ [-width/2.0, -height/2.0, width/2.0, height/2.0] ]
                        argtypes = ["std.geom.Rect<monkey.types.Float>"]
                        mesh = mojonode( c, "mojo3d.Mesh.CreateRect", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
                        return mesh.uniqueID
                elif name == "torus":
                        args = [ c.parm("radx").eval(), c.parm("rady").eval(), c.parm("cols").eval(), c.parm("rows").eval() ]
                        argtypes = ["Float","Float","Int","Int"]
                        mesh = mojonode( c, "mojo3d.Mesh.CreateTorus", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
                        return mesh.uniqueID
                elif name == "sphere":
                        args = [ c.parm("radx").eval(), c.parm("rows").eval(), c.parm("cols").eval() ]
                        argtypes = ["Float","Int","Int"]
                        mesh = mojonode( c, "mojo3d.Mesh.CreateSphere", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
                        return mesh.uniqueID
                elif name == "box":
                        args = [ getbox(c,"size"),1,1,1 ]
                        argtypes = ["std.geom.Box<monkey.types.Float>","Int","Int","Int"]
                        mesh = mojonode( c, "mojo3d.Mesh.CreateBox", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
                        return mesh.uniqueID
                elif name == "tube":
                        if c.parm("rad1").eval() == 0:
                                args = [ c.parm("rad2").eval(), c.parm("height").eval(), c.parm("orient").eval(), c.parm("cols").eval() ]
                                argtypes = ["Float", "Float", "std.geom.Axis","Int"]
                                mesh = mojonode( c, "mojo3d.Mesh.CreateCone", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
                                return mesh.uniqueID
                        else:
                                args = [ c.parm("rad2").eval(), c.parm("height").eval(), c.parm("orient").eval(), c.parm("cols").eval() ]
                                argtypes = ["Float", "Float", "std.geom.Axis","Int"]
                                mesh = mojonode( c, "mojo3d.Mesh.CreateCylinder", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
                                return mesh.uniqueID
        return None


def gettexture(n,pname, flags=12):
        texpath = n.parm(pname).eval()
        if not texpath in mojonode.byAssetPath.keys():
                if convertAssetPaths:
                        texpath=convertToAssetPath(texpath)
                args = [ texpath, flags, False ]
                argtypes = ["String", "mojo.graphics.TextureFlags", "Bool" ]
                texture = mojonode( None, "mojo3d.Scene.LoadTexture", "mojo.graphics.Texture", args, argtypes, "mojo.graphics.Texture", 1 )
                texture.json["ctor"]["inst"] = "@0"
                mojonode.byAssetPath[texpath] = texture
                return texture.uniqueID
        else:
                return mojonode.byAssetPath[texpath].uniqueID



def getcomponents():
        pass


def getModelPath(n, depth=0):
        modelpath = ""
        filemode = ""
        #exception for cameras and lights, which contain a file node
        if n.type().name().startswith("cam") or n.type().name().startswith("hlight") or n.type().name().startswith("ambient"):
                return None

        for c in n.children():
                if c.type().name() == "file":
                        file = c.parm("file").eval().split("#")
                        if file:
                                modelpath = file[0]
                                if c.parm("filemode").eval() == 2:     #file mode is "write"
                                        filemode = "write"
                                        if convertSaversToGlb:
                                                modelpath = modelpath.replace(".fbx", ".glb")
                                                modelpath = modelpath.replace(".obj", ".glb")
                                else:
                                        filemode = "read"
                                        if convertLoadersToGlb:
                                                modelpath = modelpath.replace(".fbx", ".glb")
                                                modelpath = modelpath.replace(".obj", ".glb")

                                if convertAssetPaths:
                                        modelpath = convertToAssetPath(modelpath)
                                break
                else:
                        result = getModelPath(c,depth+1)
                        if result:
                                modelpath = result[0]
                                filemode = result[1]
        return modelpath, filemode


def convertToAssetPath(originalPath):
        blocks = originalPath.split("/")
        last = len(blocks)-1
        pbr=""
        if blocks[last-1].endswith(".pbr"): pbr = blocks[last-1]+"/"
        return "asset::"+pbr+blocks[last]


def assignMaterial(n):
        if n.parm( "shop_materialpath"):
                if n.parm( "shop_materialpath").eval():
                        mojonode.byHounode[n].json["state"]["Materials"] = [getmaterial(n)]


#-------------------------------- Exporter ----------------------------------


def export():
        global convertLoadersToGlb
        global convertSaversToGlb
        global convertToAssetPaths
        global collapseHierachyOnLoad

        # path = hou.pwd().parm("path").eval()
        path = hou.ui.selectFile( "$JOB", "Choose file to export to" )

        choices = hou.ui.selectFromList(
                ("Convert Savers to .glb",
                "Convert Loaders to .glb ",
                "Convert paths to asset paths",
                "Collapse Hierarchy on Load" ),
                (1,2) )

        if 0 in choices: convertSaversToGlb=True
        if 1 in choices: convertLoadersToGlb=True
        if 2 in choices: convertToAssetPaths=True
        if 3 in choices: collapseHierachyOnLoad=True

        # clear shell
        # print "\n" * 5000
        print choices
        print "\nExporting Scene to Json file: ", path, "\n"

        #Create scene node with default state
        scene = mojonode( root, "mojo3d.Scene.New", "mojo3d.Scene", [True], ["Bool"], "Void", 0 )
        scene.json["state"]["EnvColor"] = [0,0,0,1]
        scene.json["state"]["EnvTexture"] = None
        scene.json["state"]["SkyTexture"] = None
        scene.json["state"]["AmbientLight"] = [0,0,0,1]
        scene.json["state"]["ClearColor"] = [0,0,0,1]

        #find entities, set priorities
        for c in root.children():
                inputs = c.inputs()
                if not inputs:
                        buildtree( c )

        #Assigns mojo id to each node and builds ordered node list
        index = 0
        for level in mojonode.byPriority.keys():
                for n in mojonode.byPriority[ level ]:
                        n.mojoID = "@" + str(index)
                        n.json["id"] = n.mojoID
                        orderedNodes.append( n )
                        index += 1

        #Add instances to root json dictionary
        jsondict["instances"] = []
        for n in orderedNodes:
                if "state" in n.json.keys():
                        if not n.json["state"]: n.json.pop("state")
                jsondict["instances"].append( n.json )

        #Json to text
        text = json.dumps( jsondict, sort_keys=True, indent=4, separators=(',',':') )
        text = compact( text )

        #Convert references to paths to instance ids
        for r in mojonode.byReference.keys():
                n = mojonode.byReference[r]
                text = text.replace( r, n.mojoID )

        #Finish up
        # print text
        textFile = open( path, "w+" )
        textFile.write( text )
        textFile.close()
        print "Export finished.\n"
        
        print "total mojonodes:",len(orderedNodes)
        print "mojonode priorities:",len(mojonode.byPriority)
        print "Objects by priority:"
        for l in mojonode.byPriority.values():
                for n in l:
                        if n:
                                if n.node:
                                        print n.node.name(), n.mojoID
                                else:
                                        print n.uniqueID, n.mojoID