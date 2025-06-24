from windows_toasts import InteractableWindowsToaster, Toast, WindowsToaster, ToastImagePosition,ToastActivatedEventArgs, ToastButton,ToastDisplayImage

interactableToaster = InteractableWindowsToaster("")

newToast = Toast(text_fields=['ACE-KILLER 通知', 'Hello there! You just won a thousand dollars! Click me to claim it!'])
newToast.AddImage(ToastDisplayImage.fromPath('E:/GitHub/ACE-KILLER/assets/icon/favicon.ico', position=ToastImagePosition.AppLogo))

# Add two actions (buttons)
newToast.AddAction(ToastButton('Test 1', 'response=decent', launch='https://www.google.com'))
newToast.AddAction(ToastButton('Test 2', 'response=bad', launch='https://www.github.com/'))

interactableToaster.show_toast(newToast)