"""Application entry point and non-interactive packaged startup check."""
import sys

if '--startup-check' in sys.argv:
    import os,json,traceback
    from pathlib import Path
    target=Path(sys.argv[sys.argv.index('--startup-check')+1])
    os.environ['QT_QPA_PLATFORM']='offscreen'
    try:
        from gasketfit.__main__ import main,configure_graphics  # Same import order as normal launch.
        from PySide6.QtWidgets import QApplication
        from gasketfit.padwindow import PadWindow
        configure_graphics()
        app=QApplication([])
        from gasketfit.localization import current
        current().settings.update(auto_updates=False, auto_languages=False)
        assert {'de', 'en', 'fr'} <= current().catalogs.keys(), 'Missing bundled standard languages'
        original_language = current().language
        for code, expected in [('en', 'Settings'), ('fr', 'Paramètres')]:
            current().language = code
            assert current().translate('Einstellungen') == expected
        current().language = original_language
        window=PadWindow()
        window.switch_workflow('open')
        assert window.workflow == 'open' and len(window.workflow_base().faces) > 0
        window.switch_workflow('closed')
        window.close()
        # Exercise the actual asynchronous dialog path in the shipped EXE.
        # Geometry-only tests cannot catch QDialog signal-name collisions.
        import tempfile
        from PySide6.QtCore import QEventLoop,QTimer
        from gasketfit.simple_fit_dialog import SimpleFitDialog
        app.setQuitOnLastWindowClosed(False)
        dialog=SimpleFitDialog();errors=[];dialog.failed=errors.append
        with tempfile.TemporaryDirectory() as folder:
            loop=QEventLoop();timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit)
            def calculate(kind):
                dialog.calculate(kind)
                dialog.worker.finished.connect(loop.quit);timer.start(30000);loop.exec();timer.stop()
                assert dialog.worker is None and not errors, errors
                assert kind in dialog.calculated
            calculate('arcs')
            dialog.export_arcs_to(folder)
            dialog.worker.finished.connect(loop.quit);timer.start(20000);loop.exec();timer.stop()
            assert dialog.worker is None, 'Passbogen-Export beendet sich nicht'
            assert not errors, errors
            assert dialog.tabs.isEnabled()
            from gasketfit.simple_fit import arc_filename,RADII
            assert all((Path(folder)/arc_filename(r,i)).is_file() for i,r in enumerate(RADII,1))
            dialog.adjust('centre');dialog.tabs.setCurrentIndex(2)
            before=dialog.depth_measurement.millimetres
            dialog.distance.stepUp()
            assert abs(dialog.depth_measurement.millimetres-before-.5)<1e-5
            assert dialog.viewer.items_by_name['hmd'].visible()
            dialog.height_offset.setValue(5)
            calculate('trial')
            dialog.export_one_to('trial',str(Path(folder)/'Montageprobe.3mf'))
            dialog.worker.finished.connect(loop.quit);timer.start(30000);loop.exec();timer.stop()
            assert dialog.worker is None and not errors, errors
            assert (Path(folder)/'Montageprobe.3mf').is_file()
            assert not list(Path(folder).glob('*.json'))
            dialog.tabs.setCurrentIndex(3)
            assert dialog.final_btn.isEnabled()
            calculate('final')
            dialog.export_one_to('final',str(Path(folder)/'Fertiges_Gasket.3mf'))
            dialog.worker.finished.connect(loop.quit);timer.start(30000);loop.exec();timer.stop()
            assert dialog.worker is None and not errors, errors
            assert (Path(folder)/'Fertiges_Gasket.3mf').is_file()
        dialog.close()
        target.write_text(json.dumps({'success':True,'workflows':['closed','open'],'no_scan_dialog_export':True,'adjusted_mounting_trial_export':True,'final_gasket_export':True}),encoding='utf-8')
    except BaseException:
        target.write_text(json.dumps({'success':False,'traceback':traceback.format_exc()}),encoding='utf-8')
        raise SystemExit(1)
else:
    from gasketfit.__main__ import main
    if __name__=='__main__':
        raise SystemExit(main())
